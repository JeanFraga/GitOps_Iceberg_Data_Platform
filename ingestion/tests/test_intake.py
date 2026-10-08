"""Landing intake (story 4): land, discovery, duplicates, overwrite, unmarked refusal, batch exit codes."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import ingestion.__main__ as cli
from ingestion import discover, land
from ingestion.reconcile import GateResult

MARKER = b"# SYNTHETIC-DATA-NO-REAL-PHI\n"
HEADER = (b"member_id,subscriber_id,person_code,household_id,first_name,last_name,dob,sex,address_line1,"
          b"city,state,zip,pcp_npi,coverage_start,coverage_end,ssn")  # fmt: skip
BUCKET = "p-landing"
CFG = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": {}, "profile": "demo",
       "run": {"lock_ttl_minutes": 1}}  # fmt: skip
ROW_VALUES = ("Zoe", "M1", "M2", "Ann")


def uri_for(data: bytes, name: str, date: str = "2026-10-08") -> str:
    sha = hashlib.sha256(data).hexdigest()
    return f"gs://{BUCKET}/source=payer_b/feed=members/ingest_date={date}/sha256={sha}/{name}"


class FakeGcs:
    """Fake gcloud runner + object store: ls, cat, describe, cp --if-generation-match=0."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[list[str]] = []

    def run(self, args, **kw):
        self.calls.append(list(args))
        assert args[:2] == ["gcloud", "storage"], args
        verb = args[2]
        if verb == "ls":
            out = "\n".join(sorted(self.objects)) + "\n"
            return subprocess.CompletedProcess(args, 0, out, "")
        if verb == "cp":
            src, dst = args[-2], args[-1]
            if dst in self.objects:
                return subprocess.CompletedProcess(args, 1, "", "HTTPError 412: Precondition Failed")
            self.objects[dst] = Path(src).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"unexpected gcloud verb {verb}")

    def gcloud(self, args):  # ingestion.__main__._gcloud
        self.calls.append(["gcloud", "storage", *args])
        if args[0] == "cat":
            return self.objects[args[1]]
        if args[0] == "objects":
            return b'{"storage_class": "STANDARD"}'
        raise AssertionError(args)


class FakeOps:
    """ops.file_lifecycle keyed by (sha, uri)."""

    def __init__(self):
        self.rows: list[dict] = []
        self.queries: list[str] = []

    def install(self, mp):
        lc = cli.lifecycle

        def record(**kw):
            self.rows.append({"sha": kw["file_sha256"], "uri": kw["object_uri"], "state": kw["state"],
                              "table": kw["detail"].get("table"), "branch": kw["detail"].get("branch")})  # fmt: skip

        def latest_states(**kw):
            self.queries.append("latest_states")
            return [{k: r[k] for k in ("state", "table", "branch")} for r in self.rows if r["sha"] == kw["file_sha256"]]

        def rows_for_uris(**kw):
            self.queries.append("rows_for_uris")
            out: dict = {}
            for r in self.rows:
                if r["uri"] in kw["uris"]:
                    out.setdefault(r["uri"], []).append(r["state"])
            return out

        def sha_seen_elsewhere(**kw):
            rejected = {r["uri"] for r in self.rows if r["state"] == "rejected_duplicate"}
            return any(r["sha"] == kw["file_sha256"] and r["uri"] != kw["object_uri"] and r["uri"] not in rejected
                       for r in self.rows)  # fmt: skip

        mp.setattr(lc, "record", record)
        mp.setattr(lc, "latest_states", latest_states)
        mp.setattr(lc, "rows_for_uris", rows_for_uris)
        mp.setattr(lc, "sha_seen_elsewhere", sha_seen_elsewhere)
        mp.setattr(lc, "quarantine", lambda **kw: None)
        return self

    def states(self, uri):
        return [r["state"] for r in self.rows if r["uri"] == uri]


class FakeSpark:
    def __init__(self, log):
        self.log = log

    def stop(self):
        pass


@pytest.fixture
def env(monkeypatch, tmp_path_factory):
    gcs, ops, spark_writes, fail_on = FakeGcs(), FakeOps(), [], set()
    ops.install(monkeypatch)
    monkeypatch.setattr(cli, "_gcloud", gcs.gcloud)
    monkeypatch.setattr(discover.subprocess, "run", gcs.run)
    resolved = tmp_path_factory.mktemp("cfg") / "resolved.yaml"
    resolved.write_text(json.dumps(CFG))
    monkeypatch.setattr(cli, "RESOLVED", resolved)
    monkeypatch.setattr(cli.runner, "BigQueryBackend", lambda *a: cli.runner.FakeBackend())
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: FakeSpark(spark_writes))
    monkeypatch.setattr(cli.bronze, "ensure_table", lambda *a: "ident")
    monkeypatch.setattr(cli.bronze, "published_snapshot", lambda *a: None)
    counts: dict = {}

    def write_branch(spark, ns, table, columns, rows, run_id, sha):
        if sha in fail_on:
            raise RuntimeError("spark commit failed")
        spark_writes.append(sha)
        counts[run_id + sha] = len(rows)
        return "ident", f"wap_{sha[:8]}"

    monkeypatch.setattr(cli.bronze, "write_branch", write_branch)
    monkeypatch.setattr(cli.bronze, "branch_rows", lambda *a: [])
    monkeypatch.setattr(cli.reconcile, "gate", lambda recs, rows: GateResult(True, len(recs), len(recs)))
    monkeypatch.setattr(cli.bronze, "publish", lambda *a: 42)
    published = {"n": 0}

    def bq_count(project, cap, table_ref, run_id):
        published["n"] += 1
        # pre-publish read sees 0; post-publish read sees the rows just written
        return {"rows": 0 if published["n"] % 2 else 2, "min_ordinal": 2}

    monkeypatch.setattr(cli, "bq_count", bq_count)
    return {"gcs": gcs, "ops": ops, "spark": spark_writes, "fail_on": fail_on}


def marked(body: bytes = HEADER + b"\nM1\nM2\n") -> bytes:
    return MARKER + body


def batch(capsys):
    code = cli.main(["--profile", "demo"])
    err = capsys.readouterr().err
    for v in ROW_VALUES:
        assert v not in err
    return code, [json.loads(line) for line in err.strip().splitlines()]


def test_happy_path_batch_reaches_reconciled(env, capsys):
    data = marked()
    uri = uri_for(data, "members.csv")
    env["gcs"].objects[uri] = data
    code, lines = batch(capsys)
    assert code == 0, lines
    assert env["ops"].states(uri) == ["landed", "bronze_appended", "reconciled"]
    assert lines[-1]["event"] == "batch_done" and lines[-1]["failed"] == []


def test_discovery_sources_are_only_gcloud_ls_and_lifecycle(env, capsys):
    env["gcs"].objects[uri_for(marked(), "members.csv")] = marked()
    env["fail_on"].add(hashlib.sha256(marked()).hexdigest())  # stop before any read beyond discovery matters
    batch(capsys)
    ls_calls = [c for c in env["gcs"].calls if c[2] == "ls"]
    assert ls_calls == [["gcloud", "storage", "ls", f"gs://{BUCKET}/**"]]
    assert env["ops"].queries[0] == "rows_for_uris"
    assert all(c[2] in ("ls", "cat", "objects") for c in env["gcs"].calls)


def test_land_twice_rejects_overwrite_and_keeps_object(tmp_path, env, monkeypatch, capsys):
    d = tmp_path / "payer_b" / "members"
    d.mkdir(parents=True)
    (d / "members.csv").write_bytes(marked())
    lines = []
    first = land.land_dir(tmp_path, BUCKET, "2026-10-08", lambda e, **f: lines.append({"event": e, **f}),
                          run=env["gcs"].run)  # fmt: skip
    before = dict(env["gcs"].objects)
    second = land.land_dir(tmp_path, BUCKET, "2026-10-08", lambda e, **f: lines.append({"event": e, **f}),
                           run=env["gcs"].run)  # fmt: skip
    assert len(first["landed"]) == 1 and second["rejected_overwrite"] == first["landed"]
    assert env["gcs"].objects == before
    assert lines[-1] == {"event": "land_rejected_overwrite", "uri": first["landed"][0]}


def test_main_land_exit_zero_on_overwrite_rejection(tmp_path, env, monkeypatch, capsys):
    d = tmp_path / "payer_b" / "members"
    d.mkdir(parents=True)
    (d / "members.csv").write_bytes(marked())
    (d / "other.csv").write_bytes(marked(HEADER + b"\nM9\n"))
    orig = land.land_dir
    monkeypatch.setattr(
        land, "land_dir", lambda src, bucket, date, log: orig(src, bucket, date, log, run=env["gcs"].run)
    )
    assert cli.main(["--profile", "demo", "--land", str(tmp_path)]) == 0
    env["gcs"].objects.pop(min(env["gcs"].objects))  # only one collides on the second run
    assert cli.main(["--profile", "demo", "--land", str(tmp_path)]) == 0
    events = [json.loads(x)["event"] for x in capsys.readouterr().err.strip().splitlines()]
    assert events.count("land_rejected_overwrite") == 1 and events.count("land_landed") == 3


def test_duplicate_sha_under_other_name_is_rejected_and_terminal(env, capsys):
    data = marked()
    orig, copy = uri_for(data, "members.csv"), uri_for(data, "members_copy.csv")
    env["gcs"].objects.update({orig: data, copy: data})
    code, lines = batch(capsys)
    assert code == 0
    assert env["ops"].states(orig) == ["landed", "bronze_appended", "reconciled"]
    assert env["ops"].states(copy) == ["landed", "rejected_duplicate"]
    assert env["spark"] == [hashlib.sha256(data).hexdigest()]  # one Spark write only
    assert any(x["event"] == "rejected_duplicate" and x["object_uri"] == copy for x in lines)
    # later batch: terminal, not retried
    n = len(env["ops"].rows)
    code, lines = batch(capsys)
    assert code == 0 and len(env["ops"].rows) == n
    assert next(x for x in lines if x["event"] == "discovered")["pending"] == 0


def test_original_retried_after_copy_rejected_is_not_a_duplicate(env, capsys):
    data = marked()
    orig, copy = uri_for(data, "members.csv"), uri_for(data, "members_copy.csv")
    env["gcs"].objects.update({orig: data, copy: data})
    sha = hashlib.sha256(data).hexdigest()
    env["fail_on"].add(sha)
    assert batch(capsys)[0] == 1  # original fails mid-way, copy rejected as duplicate
    assert env["ops"].states(copy) == ["landed", "rejected_duplicate"]
    env["fail_on"].clear()
    assert batch(capsys)[0] == 0
    assert env["ops"].states(orig) == ["landed", "bronze_appended", "reconciled"]


def test_redelivered_name_with_new_content_loads(env, capsys):
    a, b = marked(), marked(HEADER + b"\nM1\nM3\n")
    ua, ub = uri_for(a, "members.csv"), uri_for(b, "members.csv")
    assert ua != ub
    env["gcs"].objects.update({ua: a, ub: b})
    assert batch(capsys)[0] == 0
    assert env["ops"].states(ub)[-1] == "reconciled" and env["ops"].states(ua)[-1] == "reconciled"


def test_unmarked_landed_once_refused_no_bronze_batch_continues(env, capsys):
    unmarked = Path("tests/fixtures/marker/unmarked/members.csv").read_bytes()
    good = marked()
    uu, ug = uri_for(unmarked, "unmarked.csv"), uri_for(good, "members.csv")
    env["gcs"].objects.update({uu: unmarked, ug: good})
    code, lines = batch(capsys)
    assert code == 3
    assert env["ops"].states(uu) == ["landed"]
    assert env["ops"].states(ug)[-1] == "reconciled"
    assert any(x["event"] == "refused_unmarked" for x in lines)
    assert lines[-1]["failed"] == [uu]
    code, _ = batch(capsys)  # rerun: refused again, still exactly one `landed`
    assert code == 3 and env["ops"].states(uu) == ["landed"]


def test_non_csv_skipped_without_lifecycle_row(env, capsys):
    data = b'{"a": 1}\n'
    u = uri_for(data, "events.jsonl")
    env["gcs"].objects[u] = data
    code, lines = batch(capsys)
    assert code == 0 and env["ops"].states(u) == []
    assert any(x["event"] == "skipped_unsupported_format" for x in lines)


def test_single_file_non_csv_keeps_exit_5(env, capsys):
    data = b"x"
    assert cli.main(["--profile", "demo", "--file", uri_for(data, "e.x12")]) == 5


def test_one_failure_mid_batch_others_load(env, capsys):
    files = [marked(HEADER + f"\nM{i}\nM{i}x\n".encode()) for i in range(3)]
    uris = [uri_for(d, f"f{i}.csv") for i, d in enumerate(files)]
    env["gcs"].objects.update(dict(zip(uris, files, strict=True)))
    bad = sorted(uris)[1]
    env["fail_on"].add(bad.split("sha256=")[1].split("/")[0])
    code, lines = batch(capsys)
    assert code == 1
    for u in uris:
        assert env["ops"].states(u)[-1] == ("landed" if u == bad else "reconciled")
    assert lines[-1]["failed"] == [bad]


def test_reload_nothing_new(env, capsys):
    data = marked()
    env["gcs"].objects[uri_for(data, "members.csv")] = data
    assert batch(capsys)[0] == 0
    n = len(env["ops"].rows)
    code, _lines = batch(capsys)
    assert code == 0 and len(env["ops"].rows) == n and not env["spark"][1:]


def test_each_file_in_a_batch_gets_its_own_run_id(env, monkeypatch, capsys):
    files = [marked(HEADER + f"\nM{i}\nM{i}x\n".encode()) for i in range(2)]
    env["gcs"].objects.update({uri_for(d, f"f{i}.csv"): d for i, d in enumerate(files)})
    runs = []
    orig = cli.load
    monkeypatch.setattr(
        cli, "load", lambda cfg, uri, run_id, sfx="": (runs.append(run_id), orig(cfg, uri, run_id, sfx))[1]
    )
    assert batch(capsys)[0] == 0
    assert len(set(runs)) == 2
