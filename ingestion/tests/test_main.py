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
