import csv
import hashlib
import json
import re

import pytest

from config.fingerprint import fingerprint
from datagen import config, drift, noise
from datagen.generate import Context, generate

TOKEN = config.marker_token()
DG = config.load()["datagen"]
CI = DG["volume_profiles"]["ci"]
TRAIN = noise.scenario_set(DG["eval_only_scenarios"])
TARGETS = tuple(DG["schema_drift"])


def _ctx(targets=TARGETS):
    return Context(
        DG["seed"], "ci", CI, TOKEN, edge_case_rate=DG["edge_case_rate"], scenarios=TRAIN, schema_drift=targets
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("drift")
    return {
        "drift": (generate(_ctx(), root / "a"), root / "a"),
        "plain": (generate(_ctx(()), root / "b"), root / "b"),
    }


def _fp(path):
    text = path.read_text()
    if path.suffix == ".csv":
        return fingerprint(text.split("\n", 1)[1], "csv")
    return fingerprint(text, "jsonl")


def _base(manifest, entry):
    return re.sub(r"_drift_[a-z_]+(?=\.[a-z]+$)", "", entry["file"])


def _csv_rows(path):
    return list(csv.reader(path.read_text().splitlines()[1:]))


def test_manifest_lists_all_scenarios(runs):
    manifest, root = runs["drift"]
    entries = manifest["schema_drift"]
    assert [e["scenario"] for e in entries] == [t["scenario"] for t in TARGETS]
    paths = {f["path"] for f in manifest["files"]}
    for e, t in zip(entries, TARGETS, strict=True):
        assert set(e) == {"scenario", "source", "feed", "file", "field", "first_affected_record"}
        assert (e["source"], e["feed"], e["field"]) == (t["source"], t["feed"], t["field"])
        assert e["file"] in paths and (root / e["file"]).exists()
        assert TOKEN in (root / e["file"]).read_text()


def test_drift_visible_at_first_affected_record(runs):
    manifest, root = runs["drift"]
    for e in manifest["schema_drift"]:
        path = root / e["file"]
        lines = path.read_text().splitlines()
        line = lines[e["first_affected_record"] - 1]
        base_header = next(csv.reader([(root / _base(manifest, e)).read_text().splitlines()[1]]), None)
        if e["scenario"] == "rename_column":
            header = next(csv.reader([lines[1]]))
            assert "birth_date" in header and "dob" not in header
            assert e["first_affected_record"] == 3
            assert len(next(csv.reader([line]))) == len(header)
        elif e["scenario"] == "add_column":
            row = next(csv.reader([line]))
            assert len(row) == len(base_header) + 1 and re.fullmatch(r"PA\d{8}", row[-1])
        elif e["scenario"] == "remove_column":
            row = next(csv.reader([line]))
            assert len(row) == len(base_header) - 1
        elif e["scenario"] == "date_format":
            assert re.fullmatch(r"\d{2}/\d{2}/\d{4}", json.loads(line)["birthDate"])
            assert e["first_affected_record"] == 1
            assert "meta" in json.loads(line)
        elif e["scenario"] == "cast_failure":
            header = next(csv.reader([lines[1]]))
            i = header.index(e["field"])
            row = next(csv.reader([line]))
            assert row[i] == "N/A"
            with pytest.raises(ValueError):
                int(row[i])
            for prev in lines[2 : e["first_affected_record"] - 1]:
                int(next(csv.reader([prev]))[i])


def test_fingerprints(runs):
    manifest, root = runs["drift"]
    for e in manifest["schema_drift"]:
        same = _fp(root / e["file"]) == _fp(root / _base(manifest, e))
        assert same is (e["scenario"] in ("date_format", "cast_failure")), e["scenario"]


def test_records_conserved_and_truth_unchanged(runs):
    (md, rd), (mp, rp) = runs["drift"], runs["plain"]
    assert mp["schema_drift"] == []

    def totals(m):
        out = {}
        for f in m["files"]:
            out[(f["source"], f["feed"])] = out.get((f["source"], f["feed"]), 0) + f["records"]
        return out

    assert totals(md) == totals(mp)
    assert len(md["files"]) == len(mp["files"]) + 5
    for f in md["files"]:
        if "_drift_" in f["path"]:
            base_path = _base(md, {"file": f["path"]})
            base = next(g for g in md["files"] if g["path"] == base_path)
            assert f.get("era") == base.get("era")
    for t in ("person_truth", "coverage_spans", "encounter_claim"):
        p = f"ground_truth/{t}.jsonl"
        assert (rd / p).read_bytes() == (rp / p).read_bytes()


def test_two_scenarios_one_feed_disjoint(runs):
    (_, rd), (_, rp) = runs["drift"], runs["plain"]
    d = rd / "landing/payer_a/pharmacy"
    base = _csv_rows(d / "payer_a_pharmacy_2024.csv")[1:]
    add = _csv_rows(d / "payer_a_pharmacy_2024_drift_add_column.csv")[1:]
    cast = _csv_rows(d / "payer_a_pharmacy_2024_drift_cast_failure.csv")[1:]
    orig = _csv_rows(rp / "landing/payer_a/pharmacy/payer_a_pharmacy_2024.csv")[1:]
    k = max(1, len(orig) // 10)
    assert len(add) == len(cast) == k and len(base) == len(orig) - 2 * k
    assert [r[:-1] for r in add] == orig[len(orig) - 2 * k : len(orig) - k]
    assert base + [r[:-1] for r in add] == orig[: len(orig) - k]
    q = _csv_rows(d / "payer_a_pharmacy_2024.csv")[0].index("quantity_dispensed")
    strip = [[*r[:q], *r[q + 1 :]] for r in orig[len(orig) - k :]]
    assert [[*r[:q], *r[q + 1 :]] for r in cast] == strip


@pytest.mark.parametrize(
    "target",
    [
        {"scenario": "explode", "source": "payer_b", "feed": "members", "field": "dob"},
        {"scenario": "remove_column", "source": "payer_b", "feed": "members", "field": "nope"},
        {"scenario": "remove_column", "source": "payer_a", "feed": "837p", "field": "x"},
        {"scenario": "add_column", "source": "payer_b", "feed": "members", "field": "dob"},
        {"scenario": "remove_column", "source": "nowhere", "feed": "x", "field": "y"},
    ],
)
def test_bad_targets(tmp_path, target):
    with pytest.raises(drift.DriftError):
        generate(_ctx((target,)), tmp_path)


def test_main_reports_drift_error(monkeypatch, capsys):
    from datagen import __main__ as m

    cfg = config.load()
    cfg["datagen"]["schema_drift"] = [{"scenario": "explode", "source": "payer_b", "feed": "members", "field": "dob"}]
    monkeypatch.setattr(m.config, "load", lambda: cfg)
    monkeypatch.setattr(m, "generate", lambda ctx: generate(ctx, ctx_out))
    assert m.main(["generate"]) == 1
    assert "explode" in capsys.readouterr().err


ctx_out = None


@pytest.fixture(autouse=True)
def _out(tmp_path):
    global ctx_out
    ctx_out = tmp_path / "main"


def test_deterministic(runs, tmp_path):
    manifest, root = runs["drift"]
    again = generate(_ctx(), tmp_path / "again")

    def digest(r):
        return {
            p.relative_to(r).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob("*") if p.is_file()
        }

    assert digest(root) == digest(tmp_path / "again")
    assert again == manifest
