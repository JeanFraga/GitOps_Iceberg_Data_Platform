import csv
import hashlib
import json
import random
import subprocess

import pytest

from datagen import config, registry
from datagen.__main__ import main
from datagen.generate import Context, generate
from datagen.npi import generate_npi, is_valid_npi
from datagen.upload import UploadError, upload

TOKEN = config.marker_token()
SMALL = {"records_per_file": 300, "years": 2}


def _ctx(volume=SMALL):
    return Context(20261008, "test", volume, TOKEN)


def _hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def out(tmp_path):
    generate(_ctx(), tmp_path / "out")
    return tmp_path / "out"


def test_deterministic(tmp_path):
    generate(_ctx(), tmp_path / "a")
    generate(_ctx(), tmp_path / "b")
    assert _hashes(tmp_path / "a") == _hashes(tmp_path / "b")


def test_marker_in_every_data_file(out):
    data = [p for p in out.rglob("*") if p.suffix in (".csv", ".jsonl")]
    assert data
    for p in data:
        assert TOKEN.encode() in p.read_bytes()[:4096]
        if p.suffix == ".jsonl":
            for line in p.read_text().splitlines():
                assert next(iter(json.loads(line))) == "_synthetic"
        else:
            assert p.read_text().startswith(f"# {TOKEN}\n")


def test_manifest_shape_and_sha(out):
    m = json.loads((out / "manifest.json").read_text())
    assert m["_synthetic"] == TOKEN and m["seed"] == 20261008 and m["volume_profile"] == "test"
    assert m["schema_drift"] == [] and m["data_drift"] == []
    paths = [f["path"] for f in m["files"]]
    e834 = [p for p in paths if p.endswith(".834")]
    assert e834[-1] == "landing/payer_a/834/payer_a_834_full_20240101.834" and len(e834) >= 2
    assert [p for p in paths if not p.endswith(".834")] == [
        *(f"landing/payer_a/835/payer_a_835_{k}_{e}.835" for k in "dip" for e in ("A1", "A2")),
        *(f"landing/payer_a/837{k}/payer_a_837{k}_{e}.837" for k in "dip" for e in ("A1", "A2")),
        "landing/payer_a/pharmacy/payer_a_pharmacy_2024.csv",
        "landing/payer_a/pharmacy/payer_a_pharmacy_2025.csv",
        "landing/payer_b/members/payer_b_members_2024.csv",
        "landing/payer_b/members/payer_b_members_2025.csv",
        "landing/provider_directory/providers/providers.csv",
    ]
    for f in m["files"]:
        assert f["sha256"] == hashlib.sha256((out / f["path"]).read_bytes()).hexdigest()
        assert f["records"] <= SMALL["records_per_file"]
    truth = (out / "ground_truth" / "person_truth.jsonl").read_text().splitlines()
    pb = [f for f in m["files"] if f["source"] == "payer_b"]
    assert pb[0]["records"] == len([r for r in map(json.loads, truth) if r.get("source") == "payer_b"])


def test_csv_members_in_person_truth(out):
    truth = [json.loads(line) for line in (out / "ground_truth" / "person_truth.jsonl").read_text().splitlines()]
    truth_ids = {r["source_record_id"] for r in truth if r.get("source") == "payer_b"}
    for path in (out / "landing" / "payer_b" / "members").iterdir():
        rows = list(csv.DictReader(path.read_text().splitlines()[1:]))
        assert len(rows) == len(truth_ids) <= SMALL["records_per_file"]
        assert {r["member_id"] for r in rows} == truth_ids
        assert rows == sorted(rows, key=lambda r: (r["subscriber_id"], r["person_code"]))
        assert all(is_valid_npi(r["pcp_npi"]) for r in rows)
    names = (out / "names.txt").read_text().splitlines()
    assert names == sorted(set(names)) and names


def test_npi_luhn_and_prefix():
    assert is_valid_npi("1234567893")  # CMS worked example
    assert not is_valid_npi("1234567890")
    rng = random.Random(1)
    for _ in range(500):
        npi = generate_npi(rng)
        assert npi.startswith("29") and is_valid_npi(npi)


def test_registry_discovers_payer_b():
    feeds = registry.discover()
    assert ("payer_b", "members") in [(f.source, f.feed) for f in feeds]


def test_unknown_volume_errors(capsys):
    with pytest.raises(config.VolumeError, match="ci, full"):
        config.resolve_volume(config.load(), "huge")
    assert main(["generate", "--volume", "huge"]) == 1
    assert "valid: ci, full" in capsys.readouterr().err


def test_volume_override_wins():
    cfg = config.load()
    assert config.resolve_volume(cfg, "full")[0] == "full"
    assert config.resolve_volume(cfg)[0] == cfg["datagen"]["volume_profile"]


class FakeRun:
    def __init__(self, landed=""):
        self.calls, self.landed = [], landed

    def __call__(self, args, **kw):
        self.calls.append(args)
        stdout = self.landed if args[:3] == ["gcloud", "storage", "ls"] else ""
        return subprocess.CompletedProcess(args, 0 if stdout or args[2] != "ls" else 1, stdout, "")


CFG = {"project_id": "proj-x", "cost": {"max_bytes_billed": 1000}}


def test_upload_copies_then_delete_and_load(out):
    run = FakeRun()
    upload(CFG, out, run, ingest_date="2026-10-08")
    m = json.loads((out / "manifest.json").read_text())
    cps = [c for c in run.calls if c[:3] == ["gcloud", "storage", "cp"]]
    assert len(cps) == len(m["files"]) and len(m["files"]) >= 16
    pb = next(i for i, f in enumerate(m["files"]) if f["source"] == "payer_b")
    sha = m["files"][pb]["sha256"]
    assert cps[pb][3] == "--if-generation-match=0"
    assert cps[pb][5] == (
        f"gs://proj-x-landing/source=payer_b/feed=members/ingest_date=2026-10-08/sha256={sha}/payer_b_members_2024.csv"
    )
    bq = [c for c in run.calls if c[0] == "bq"]
    assert bq[0][:3] == ["bq", "--project_id=proj-x", "query"]
    assert "--maximum_bytes_billed=1000" in bq[0]
    assert bq[0][-1] == "DELETE FROM mpi_eval.ground_truth WHERE generator_seed = 20261008"
    assert bq[1][2] == "load" and bq[1][-2] == "mpi_eval.ground_truth"
    assert "--ignore_unknown_values" in bq[1]


def test_upload_skips_landed_sha(out):
    m = json.loads((out / "manifest.json").read_text())
    listing = "".join(
        f"gs://proj-x-landing/source={f['source']}/feed={f['feed']}/ingest_date=2026-01-01/sha256={f['sha256']}/x.csv\n"
        for f in m["files"]
    )
    run = FakeRun(listing)
    log = upload(CFG, out, run, ingest_date="2026-10-08")
    assert not [c for c in run.calls if c[:3] == ["gcloud", "storage", "cp"]]
    assert sum("already landed" in line for line in log) == len(m["files"])


def test_upload_without_generate(tmp_path):
    with pytest.raises(UploadError, match="run make generate first"):
        upload(CFG, tmp_path, FakeRun())


def test_person_code_roles_and_whole_households(out):
    path = out / "landing" / "payer_b" / "members" / "payer_b_members_2024.csv"
    rows = list(csv.DictReader(path.read_text().splitlines()[1:]))
    hh_by_id = {h.household_id: h for h in _ctx().population(SMALL["records_per_file"])}
    by_sub: dict[str, list[dict]] = {}
    for r in rows:
        by_sub.setdefault(r["subscriber_id"], []).append(r)
    for group in by_sub.values():
        hh = hh_by_id[group[0]["household_id"]]
        assert len(group) == len(hh.members)  # no partial household
        expected = (
            ["01"]
            + (["02"] if hh.has_spouse else [])
            + [f"{i:02d}" for i in range(3, 3 + len(group) - 1 - hh.has_spouse)]
        )
        assert [r["person_code"] for r in group] == expected
        assert all(r["member_id"].endswith("-" + r["person_code"]) for r in group)
