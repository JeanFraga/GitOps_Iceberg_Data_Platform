import hashlib
import json
import os
import subprocess

import pytest

from ingestion.edi import __main__ as cli
from ingestion.edi import check
from ingestion.edi.preparse import preparse
from ingestion.records import split

ISA = b"ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240101*1200*^*00501*000000042*0*T*:~"
NESTED = ISA + (
    b"\nGS*HC*S*R*20240101*1200*7*X*005010X222A1~ST*837*0001~BHT*0019*00*SYNTHETIC-DATA-NO-REAL-PHI~SE*3*0001~"
    b"ST*837*0002~NM1*41*2~SE*3*0002~GE*2*7~IEA*1*000000042~"
)


def rows(body: bytes) -> list[dict]:
    return [json.loads(line) for line in body.decode("utf-8").splitlines()]


def test_isa_is_full_length():
    assert len(ISA) == 106


def test_nested_controls():
    r = {(x["segment_id"], x["segment_ordinal"]): x for x in rows(preparse(NESTED, "n.837"))}
    ctl = {k: (v["isa_control"], v["gs_control"], v["st_control"]) for k, v in r.items()}
    assert ctl[("ISA", 1)] == ("000000042", None, None)
    assert ctl[("GS", 2)] == ("000000042", "7", None)
    assert ctl[("BHT", 4)] == ("000000042", "7", "0001")
    assert ctl[("SE", 5)] == ("000000042", "7", "0001")
    assert ctl[("NM1", 7)] == ("000000042", "7", "0002")
    assert ctl[("GE", 9)] == ("000000042", "7", None)
    assert ctl[("IEA", 10)] == ("000000042", None, None)
    assert r[("BHT", 4)]["elements"] == ["BHT", "0019", "00", "SYNTHETIC-DATA-NO-REAL-PHI"]


def test_deterministic_format():
    body = preparse(NESTED, "n.837")
    assert body == preparse(NESTED, "n.837")
    assert body.endswith(b"\n") and b"\r" not in body
    for line in body.decode("utf-8").splitlines():
        obj = json.loads(line)
        assert list(obj) == sorted(obj) == sorted(check_keys())
        assert line == json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert obj["source_sha256"] == hashlib.sha256(NESTED).hexdigest()


def check_keys():
    from ingestion.edi.preparse import KEYS

    return KEYS


@pytest.mark.parametrize("sample", check.samples(), ids=lambda p: p.name)
def test_segment_count_matches_split(sample):
    data = sample.read_bytes()
    out = rows(preparse(data, sample.name))
    assert [r["segment_ordinal"] for r in out] == list(range(1, len(split(data, "x12")) + 1))


def test_bad_input_raises():
    with pytest.raises(ValueError):
        preparse(b"GS*HC~", "x.837")


def test_cli_bad_input_exit_1(tmp_path):
    f = tmp_path / "bad.837"
    f.write_bytes(b"not x12")
    assert cli.main([str(f), "--out", str(tmp_path)]) == 1


def test_cli_local_leaves_raw_untouched(tmp_path):
    f = tmp_path / "n.837"
    f.write_bytes(NESTED)
    before = (os.stat(f).st_mtime_ns, os.stat(f).st_size, hashlib.sha256(f.read_bytes()).hexdigest())
    out = tmp_path / "out"
    assert cli.main([str(f), "--out", str(out)]) == 0
    assert (out / "n.837.jsonl").read_bytes() == preparse(NESTED, "n.837")
    assert (os.stat(f).st_mtime_ns, os.stat(f).st_size, hashlib.sha256(f.read_bytes()).hexdigest()) == before


def test_cli_landing_writes_one_object(monkeypatch, tmp_path):
    resolved = tmp_path / "resolved.yaml"
    resolved.write_text("project_id: proj\n")
    monkeypatch.setattr(cli, "RESOLVED", resolved)
    src = "gs://proj-landing/source=payer_a/feed=837p/ingest_date=2026-10-08/sha256=" + "a" * 64 + "/n.837"
    calls = []

    def run(args, **kw):
        calls.append((args, kw))
        if args[2] == "cat":
            return subprocess.CompletedProcess(args, 0, NESTED, b"")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    assert cli.main([src, "--landing", "--source", "payer_a", "--feed", "837p"], run=run) == 0
    writes = [c for c in calls if c[0][2] != "cat"]
    assert len(writes) == 1
    sha = hashlib.sha256(NESTED).hexdigest()
    args, kw = writes[0]
    assert args[-1] == f"gs://proj-warehouse/edi_preparse/source=payer_a/feed=837p/sha256={sha}/n.837.jsonl"
    assert "--if-generation-match=0" in args and kw["input"] == preparse(NESTED, "n.837")
    assert all("proj-landing" not in a for a, _ in writes for a in a[:-1]) and src not in args


def test_check_detects_changed_golden(tmp_path, monkeypatch):
    golden = tmp_path / "golden"
    monkeypatch.setattr(check, "GOLDEN", golden)
    assert check.main(["--update"]) == 0
    assert check.main([]) == 0
    victim = min(golden.glob("*.sha256"))
    b = bytearray(victim.read_bytes())
    b[0] = ord("0") if b[0] != ord("0") else ord("1")
    victim.write_bytes(bytes(b))
    assert check.main([]) == 1


def test_non_utf8_segment_kept_as_base64():
    import base64

    data = NESTED.replace(b"NM1*41*2~", b"NM1*41*\xff\xfe~")
    r = {x["segment_ordinal"]: x for x in rows(preparse(data, "n.837"))}
    bad = r[7]
    assert bad["elements"] is None and bad["segment_id"] == "NM1" and bad["encoding"] != "utf-8"
    assert base64.b64decode(bad["raw_b64"]) == b"NM1*41*\xff\xfe"
    assert (bad["isa_control"], bad["gs_control"], bad["st_control"]) == ("000000042", "7", "0002")
    assert "raw_b64" not in r[6]


def _landing(monkeypatch, tmp_path, existing):
    resolved = tmp_path / "resolved.yaml"
    resolved.write_text("project_id: proj\n")
    monkeypatch.setattr(cli, "RESOLVED", resolved)

    def run(args, **kw):
        if args[2] == "cat":
            body = NESTED if args[3].startswith("gs://proj-landing") else existing
            return subprocess.CompletedProcess(args, 0, body, b"")
        return subprocess.CompletedProcess(args, 1, b"", b"HTTPError 412: Precondition Failed")

    src = "gs://proj-landing/source=payer_a/feed=837p/sha256=" + "a" * 64 + "/n.837"
    return cli.main([src, "--landing", "--source", "payer_a", "--feed", "837p"], run=run)


def test_landing_existing_equal_is_ok(monkeypatch, tmp_path):
    assert _landing(monkeypatch, tmp_path, preparse(NESTED, "n.837")) == 0


def test_landing_existing_different_is_conflict(monkeypatch, tmp_path, capsys):
    assert _landing(monkeypatch, tmp_path, b"stale\n") == 1
    assert "edi_preparse_conflict" in capsys.readouterr().err


def test_landing_missing_resolved_exit_1(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "RESOLVED", tmp_path / "nope.yaml")
    f = tmp_path / "n.837"
    f.write_bytes(NESTED)
    assert cli.main([str(f), "--landing", "--source", "s", "--feed", "f"]) == 1


def test_out_and_landing_are_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["x.837", "--out", str(tmp_path), "--landing", "--source", "s", "--feed", "f"])
    with pytest.raises(SystemExit):
        cli.main(["x.837", "--source", "s"])


def test_check_detects_changed_first_st_golden(tmp_path, monkeypatch):
    golden = tmp_path / "golden"
    monkeypatch.setattr(check, "GOLDEN", golden)
    assert check.main(["--update"]) == 0
    victim = next(golden.glob("*.first_st.jsonl"))
    victim.write_bytes(victim.read_bytes().replace(b'"ISA"', b'"ISB"', 1))
    assert check.main([]) == 1
