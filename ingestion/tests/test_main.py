import hashlib
import json

import pytest

import ingestion.__main__ as cli
from ingestion.marker import UnmarkedFile

CFG = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": {}}


def test_unmarked_refused_before_any_lifecycle_or_bronze_write(monkeypatch, capsys):
    data = b"member_id,ssn\nM1,Zoe\n"
    sha = hashlib.sha256(data).hexdigest()
    uri = f"gs://b/source=payer_b/feed=members/ingest_date=2026-10-08/sha256={sha}/x.csv"
    monkeypatch.setattr(cli, "_gcloud", lambda args: data)
    writes = []
    monkeypatch.setattr(cli.lifecycle, "record", lambda **kw: writes.append(kw))
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: pytest.fail("Spark started"))
    with pytest.raises(UnmarkedFile):
        cli.load(CFG, uri, "run-1")
    assert writes == []
    err = capsys.readouterr().err
    line = json.loads(err.strip().splitlines()[-1])
    assert line["event"] == "refused_unmarked" and line["file_sha256"] == sha
    assert "Zoe" not in err and "M1" not in err


def test_sha_mismatch_with_landed_path_is_refused(monkeypatch):
    monkeypatch.setattr(cli, "_gcloud", lambda args: b"x")
    with pytest.raises(ValueError, match="does not match"):
        cli.load(CFG, "gs://b/source=s/feed=f/ingest_date=d/sha256=" + "0" * 64 + "/x.csv", "r")


def test_main_unmarked_exits_nonzero_with_clean_error_line(monkeypatch, capsys):
    data = b"member_id,first_name\nM1,Zoe\n"
    sha = hashlib.sha256(data).hexdigest()
    uri = f"gs://b/source=payer_b/feed=members/ingest_date=2026-10-08/sha256={sha}/x.csv"
    cfg = {**CFG, "profile": "demo", "run": {"lock_ttl_minutes": 1}}
    monkeypatch.setattr(cli.yaml, "safe_load", lambda _: cfg)
    monkeypatch.setattr(cli.runner, "BigQueryBackend", lambda *a: cli.runner.FakeBackend())
    monkeypatch.setattr(cli, "_gcloud", lambda args: data)
    monkeypatch.setattr(cli.lifecycle, "record", lambda **kw: pytest.fail("lifecycle written"))
    assert cli.main(["--profile", "demo", "--file", uri]) != 0
    err = capsys.readouterr().err
    last = json.loads(err.strip().splitlines()[-1])
    assert last["event"] == "error" and last["error_type"] == "UnmarkedFile"
    assert "Zoe" not in err and "M1" not in err


class FakeOps:
    """Stands in for ops.file_lifecycle / ops.quarantine (bq CLI)."""

    def __init__(self, seen=()):
        self.lifecycle = [dict(s) for s in seen]
        self.quarantine = []

    def install(self, monkeypatch):
        monkeypatch.setattr(cli.lifecycle, "record", lambda **kw: self.lifecycle.append(
            {"state": kw["state"], "table": kw["detail"].get("table"), "branch": kw["detail"].get("branch"),
             "detail": kw["detail"]}))  # fmt: skip
        monkeypatch.setattr(
            cli.lifecycle,
            "latest_states",
            lambda **kw: [{k: s.get(k) for k in ("state", "table", "branch")} for s in self.lifecycle],
        )
        monkeypatch.setattr(cli.lifecycle, "quarantine", lambda **kw: self.quarantine.append(kw))
        return self

    @property
    def states(self):
        return [s["state"] for s in self.lifecycle]


def marked(body=b"member_id,first_name\nM1,Zoe\nM2,Ann\n"):
    data = b"# SYNTHETIC-DATA-NO-REAL-PHI\n" + body
    sha = hashlib.sha256(data).hexdigest()
    return data, sha, f"gs://b/source=payer_b/feed=members/ingest_date=2026-10-08/sha256={sha}/x.csv"


def fake_gcloud(data):
    return lambda args: b'{"storage_class": "STANDARD"}' if args[0] == "objects" else data


def test_reload_skips_without_spark_or_lifecycle_rows(monkeypatch, capsys):
    data, _sha, uri = marked()
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    seen = [
        {"state": "landed", "table": None},
        {"state": "bronze_appended", "table": "bronze_payer_b.members__era_2024"},
    ]
    ops = FakeOps(seen).install(monkeypatch)
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: pytest.fail("Spark started"))
    out = cli.load(CFG, uri, "run-2")
    assert out["skipped"] == "already_appended" and len(ops.lifecycle) == 2
    assert json.loads(capsys.readouterr().err.strip().splitlines()[-1])["event"] == "skipped_already_appended"


def test_other_table_suffix_is_not_skipped_and_landed_is_written_once(monkeypatch):
    data, _sha, uri = marked()
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    seen = [
        {"state": "landed", "table": None},
        {"state": "bronze_appended", "table": "bronze_payer_b.members__era_2024"},
    ]
    ops = FakeOps(seen).install(monkeypatch)

    def boom(*a):
        raise RuntimeError("stop before Spark")

    monkeypatch.setattr(cli.bronze, "build_session", boom)
    with pytest.raises(RuntimeError):
        cli.load(CFG, uri, "run-3", "_wap")
    assert ops.states == ["landed", "bronze_appended"]  # no second `landed`


def test_failure_during_branch_write_leaves_no_bronze_appended(monkeypatch):
    data, _sha, uri = marked()
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    ops = FakeOps().install(monkeypatch)

    class Spark:
        def stop(self):
            pass

    def fail_write(*a):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: Spark())
    monkeypatch.setattr(cli.bronze, "ensure_table", lambda *a: "ident")
    monkeypatch.setattr(cli.bronze, "published_snapshot", lambda *a: None)
    monkeypatch.setattr(cli.bronze, "write_branch", fail_write)
    monkeypatch.setattr(cli.bronze, "publish", lambda *a: pytest.fail("published"))
    with pytest.raises(RuntimeError):
        cli.load(CFG, uri, "run-4")
    assert ops.states == ["landed"]


def test_main_reconcile_fail_exit_code_and_type_only_log(monkeypatch, capsys):
    _data, _sha, uri = marked()
    cfg = {**CFG, "profile": "demo", "run": {"lock_ttl_minutes": 1}}
    monkeypatch.setattr(cli.yaml, "safe_load", lambda _: cfg)
    monkeypatch.setattr(cli.runner, "BigQueryBackend", lambda *a: cli.runner.FakeBackend())

    def fail(*a, **k):
        raise cli.ReconcileFail("RECONCILE_FAIL")

    monkeypatch.setattr(cli, "load", fail)
    assert cli.main(["--profile", "demo", "--file", uri]) == 4
    last = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert last["error_type"] == "ReconcileFail"
