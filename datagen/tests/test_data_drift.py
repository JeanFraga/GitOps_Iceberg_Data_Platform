import csv
import hashlib
import re

import pytest

from datagen import config, data_drift, noise, registry
from datagen.generate import Context, generate

TOKEN = config.marker_token()
DG = config.load()["datagen"]
CI = DG["volume_profiles"]["ci"]
TRAIN = noise.scenario_set(DG["eval_only_scenarios"])
SCHEMA = tuple(DG["schema_drift"])
TARGETS = tuple(DG["data_drift"])


def _ctx(targets=TARGETS, schema=SCHEMA):
    return Context(
        DG["seed"],
        "ci",
        CI,
        TOKEN,
        edge_case_rate=DG["edge_case_rate"],
        scenarios=TRAIN,
        schema_drift=schema,
        data_drift=targets,
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("data_drift")
    return {
        "drift": (generate(_ctx(), root / "a"), root / "a"),
        "again": (generate(_ctx(), root / "c"), root / "c"),
        "plain": (generate(_ctx(()), root / "b"), root / "b"),
    }


def _base(entry):
    return re.sub(r"_datadrift_[a-z_]+(?=\.[a-z]+$)", "", entry["file"])


def _values(path, field):
    lines = path.read_text().splitlines()
    rows = list(csv.reader(lines[1:]))
    i = rows[0].index(field)
    return [r[i] for r in rows[1:]]


def _stat(scenario, base, drifted):
    if scenario == "code_mix":
        keys = set(base) | set(drifted)
        return 0.5 * sum(abs(base.count(k) / len(base) - drifted.count(k) / len(drifted)) for k in keys)
    if scenario == "null_rate":
        return abs(drifted.count("") / len(drifted) - base.count("") / len(base))

    def mean(v):
        nums = [float(x) for x in v if x not in ("", "N/A")]
        return sum(nums) / len(nums)

    return abs(mean(drifted) / mean(base) - 1)


def test_manifest_lists_all_scenarios(runs):
    manifest, root = runs["drift"]
    entries = manifest["data_drift"]
    assert [e["scenario"] for e in entries] == [t["scenario"] for t in TARGETS]
    paths = {f["path"] for f in manifest["files"]}
    for e, t in zip(entries, TARGETS, strict=True):
        assert set(e) == {"scenario", "source", "feed", "file", "field", "magnitude", "first_affected_record"}
        assert (e["source"], e["feed"], e["field"], e["magnitude"]) == (
            t["source"],
            t["feed"],
            t["field"],
            t["magnitude"],
        )
        assert "_datadrift_" in e["file"] and e["file"] in paths
        assert TOKEN in (root / e["file"]).read_text().splitlines()[0]


def test_measured_drift_exceeds_magnitude(runs):
    manifest, root = runs["drift"]
    eras = {f["path"]: f.get("era") for f in manifest["files"]}
    for e in manifest["data_drift"]:
        assert eras[e["file"]] == eras[_base(e)]
        stat = _stat(e["scenario"], _values(root / _base(e), e["field"]), _values(root / e["file"], e["field"]))
        assert stat > e["magnitude"], (e["scenario"], stat)


def test_first_affected_record_changed(runs):
    manifest, root = runs["drift"]
    for e in manifest["data_drift"]:
        lines = (root / e["file"]).read_text().splitlines()
        header = next(csv.reader([lines[1]]))
        i = header.index(e["field"])
        row = next(csv.reader([lines[e["first_affected_record"] - 1]]))
        if e["scenario"] == "code_mix":
            assert row[i] in ("1", "2")
        elif e["scenario"] == "null_rate":
            assert row[i] == ""
        assert e["first_affected_record"] >= 3


def test_records_preserved_and_schema_drift_untouched(runs):
    with_dd, root_a = runs["drift"]
    plain, root_b = runs["plain"]
    assert plain["data_drift"] == []
    for key in ("payer_b/members", "payer_a/pharmacy"):
        total = [sum(f["records"] for f in m["files"] if f"landing/{key}/" in f["path"]) for m in (with_dd, plain)]
        assert total[0] == total[1]
    assert with_dd["schema_drift"] == plain["schema_drift"]
    for e in plain["schema_drift"]:
        assert (root_a / e["file"]).read_bytes() == (root_b / e["file"]).read_bytes()


def test_no_data_drift_output_unchanged(tmp_path):
    m = generate(_ctx(()), tmp_path / "x")
    assert m["data_drift"] == []
    assert not [f for f in m["files"] if "_datadrift_" in f["path"]]


def _digest(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_byte_identical_runs(runs):
    assert _digest(runs["drift"][1]) == _digest(runs["again"][1])


@pytest.mark.parametrize(
    "bad",
    [
        {**TARGETS[0], "scenario": "bogus"},
        {**TARGETS[0], "field": "no_such_field"},
        {k: v for k, v in TARGETS[0].items() if k != "codes"},
        {**TARGETS[1], "rate": 0},
        {**TARGETS[2], "factor": 1},
        {k: v for k, v in TARGETS[2].items() if k != "magnitude"},
        {**TARGETS[0], "source": "nope"},
    ],
)
def test_bad_target_raises(tmp_path, bad):
    with pytest.raises(data_drift.DataDriftError):
        generate(_ctx((bad,), ()), tmp_path / "x")
    assert not (tmp_path / "x" / "landing").exists()


def test_x12_feed_rejected(tmp_path):
    x12 = next(f for f in registry.discover() if f.source == "payer_a" and "83" in f.feed)
    bad = {
        "scenario": "code_mix",
        "source": x12.source,
        "feed": x12.feed,
        "field": "x",
        "codes": ["1"],
        "magnitude": 0.1,
    }
    with pytest.raises(data_drift.DataDriftError):
        generate(_ctx((bad,), ()), tmp_path / "x", feeds=[x12])


def test_ndjson_null_is_json_null():
    from datagen.drift import _Chunk

    chunk = _Chunk("ndjson", None, [{"a": 1}, {"a": 2}])
    data_drift._null_rate(chunk, {"field": "a", "rate": 1}, __import__("random").Random(0))
    assert all(r["a"] is None for r in chunk.records)
