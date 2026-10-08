import copy
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from itertools import combinations

import pytest

from datagen import config, noise
from datagen.__main__ import main
from datagen.generate import Context, generate
from datagen.population import Address

TOKEN = config.marker_token()
CFG = config.load()
DG = CFG["datagen"]
CI = DG["volume_profiles"]["ci"]
TRAIN = noise.scenario_set(DG["eval_only_scenarios"])


def _ctx(run="train", **kw):
    seed = DG["eval_seed"] if run == "eval" else DG["seed"]
    scen = noise.scenario_set() if run == "eval" else TRAIN
    return Context(seed, "ci", CI, TOKEN, edge_case_rate=DG["edge_case_rate"], scenarios=scen, run=run, **kw)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("noise")
    out = {}
    for run in ("train", "eval"):
        out[run] = (generate(_ctx(run), root / run), root / run)
    return out


def _truth(root):
    return [json.loads(line) for line in (root / "ground_truth" / "person_truth.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("run", ["train", "eval"])
def test_truth_rows_and_pair_rate(runs, run):
    manifest, root = runs[run]
    rows = _truth(root)
    keys = [(r["source"], r["source_record_id"]) for r in rows]
    assert len(keys) == len(set(keys))  # one person per record
    for r in rows:
        assert r["person_truth"].startswith("P")
        assert r["noise_type"] is None or r["noise_type"] in noise.SCENARIOS
    truth_keys = set(keys)
    with open(next((root / "landing" / "payer_b" / "members").glob("*.csv"))) as f:
        lines = [line for line in f if not line.startswith("#")]
    reader = list(csv.DictReader(lines))
    assert list(reader[0])[-1] == "ssn"
    assert {("payer_b", m["member_id"]) for m in reader} <= truth_keys
    for line in next((root / "landing" / "emr_facility_1" / "patient").glob("*.ndjson")).read_text().splitlines():
        assert ("emr_facility_1", json.loads(line)["id"]) in truth_keys
    for p in (root / "landing" / "payer_a" / "834").glob("*.834"):
        for seg in p.read_text().split("~"):
            if seg.strip().startswith("REF*0F*"):
                assert ("payer_a", seg.strip().split("*")[2]) in truth_keys
    by_person = defaultdict(list)
    for r in rows:
        by_person[r["person_truth"]].append(r["noise_type"] is not None)
    pairs = [a or b for flags in by_person.values() for a, b in combinations(flags, 2)]
    assert len(pairs) > 1000
    assert 0.015 <= sum(pairs) / len(pairs) <= 0.025
    assert manifest["run"] == run
    assert manifest["edge_case_rate"] == DG["edge_case_rate"]
    assert manifest["noise_scenarios"] == sorted({r["noise_type"] for r in rows if r["noise_type"]})


def test_eval_has_scenario_absent_from_train(runs):
    train, ev = set(runs["train"][0]["noise_scenarios"]), set(runs["eval"][0]["noise_scenarios"])
    assert not train & set(DG["eval_only_scenarios"])
    assert ev - train


def test_noisy_names_listed(runs):
    _, root = runs["train"]
    names = set((root / "names.txt").read_text().splitlines())
    with open(next((root / "landing" / "payer_b" / "members").glob("*.csv"))) as f:
        reader = csv.DictReader(line for line in f if not line.startswith("#"))
        assert {f"{m['first_name']} {m['last_name']}" for m in reader} <= names


def _hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("run", ["train", "eval"])
def test_deterministic(runs, tmp_path, run):
    generate(_ctx(run), tmp_path / "again")
    assert _hashes(tmp_path / "again") == _hashes(runs[run][1])


def test_rate_zero_no_noise(tmp_path):
    ctx = Context(1, "t", {"records_per_file": 300, "years": 1}, TOKEN, edge_case_rate=0.0)
    m = generate(ctx, tmp_path / "o")
    assert m["noise_scenarios"] == []
    assert all(r["noise_type"] is None for r in _truth(tmp_path / "o"))


def test_unknown_eval_only_name(monkeypatch, capsys):
    cfg = copy.deepcopy(CFG)
    cfg["datagen"]["eval_only_scenarios"] = ["twin", "bogus_scenario"]
    monkeypatch.setattr(config, "load", lambda: cfg)
    assert main(["generate"]) == 1
    assert "bogus_scenario" in capsys.readouterr().err
    with pytest.raises(noise.ScenarioError):
        noise.scenario_set(["nope"])


def test_ssn_shape():
    s = noise.ssn("P00000001")
    assert len(s) == 9 and s.isdigit() and s[0] == "9" and s == noise.ssn("P00000001")


ADDR = Address("12 Oak St", "Springfield", "IL", "62701")
POOL = (ADDR, Address("9 Elm Rd", "Riverton", "WY", "82501"))
ADULT_M = noise.Identity("Samuel", "Holloway", date(1980, 3, 7), "M", ADDR, noise.ssn("P1"))
BABY_F = noise.Identity("Olivia", "Holloway", date(2024, 6, 20), "F", ADDR, noise.ssn("P2"))


class _Ctx:
    def __init__(self, scenarios, rate=1.0, seed=7):
        self.seed, self.edge_case_rate, self.scenarios = seed, rate, scenarios


@pytest.mark.parametrize("name", list(noise.SCENARIOS))
def test_each_scenario_changes_written_fields(name):
    base = BABY_F if name == "newborn_placeholder" else ADULT_M
    sc = noise.SCENARIOS[name]
    assert sc.applies("payer_b", base)
    got = noise.decide(_Ctx((name,)), "payer_b", "R1", base, POOL)
    assert got.noise_type == name
    fields = ("first_name", "last_name", "dob", "sex", "address", "ssn")
    assert any(getattr(got, f) != getattr(base, f) for f in fields)


def test_scenario_specifics():
    import random

    r = random.Random(1)
    assert noise.SCENARIOS["dob_day_month_swap"].apply(r, ADULT_M, POOL).dob == date(1980, 7, 3)
    assert noise.SCENARIOS["nickname"].apply(r, ADULT_M, POOL).first_name == "Sam"
    assert noise.SCENARIOS["ssn_last4"].apply(r, ADULT_M, POOL).ssn == ADULT_M.ssn[-4:]
    assert noise.SCENARIOS["ssn_default"].apply(r, ADULT_M, POOL).ssn == "999999999"
    assert noise.SCENARIOS["shared_household"].apply(r, ADULT_M, POOL).address == POOL[1]
    assert noise.SCENARIOS["newborn_placeholder"].apply(r, BABY_F, POOL).first_name == "BABY GIRL"
    assert not noise.SCENARIOS["move"].applies("payer_a", ADULT_M)
    assert not noise.SCENARIOS["ssn_missing"].applies("payer_a", ADULT_M)
    assert not noise.SCENARIOS["cross_payer_switch"].applies("emr_facility_1", ADULT_M)
    assert not noise.SCENARIOS["newborn_placeholder"].applies("payer_b", ADULT_M)


def test_day_over_12_never_swapped():
    ident = noise.Identity("Samuel", "Holloway", date(1980, 3, 17), "M", ADDR, "912345678")
    assert not noise.SCENARIOS["dob_day_month_swap"].applies("payer_b", ident)
    seen = {noise.decide(_Ctx(tuple(noise.SCENARIOS)), "payer_b", f"R{i}", ident, POOL).noise_type for i in range(400)}
    assert "dob_day_month_swap" not in seen and len(seen) > 5


def test_rate_zero_decide_clean():
    assert noise.decide(_Ctx(tuple(noise.SCENARIOS), rate=0.0), "payer_b", "R1", ADULT_M, POOL) is ADULT_M
