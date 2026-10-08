import hashlib
import json
import re

import pytest

from datagen import config
from datagen.generate import Context, generate

TOKEN = config.marker_token()
CI = {"records_per_file": 300, "years": 1}
FEEDS = ("patient", "practitioner", "organization", "encounter")


def _run(root):
    generate(Context(20261008, "ci", CI, TOKEN), root)
    return root


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("fhir") / "out")


def _lines(out, feed):
    return (out / "landing" / "emr_facility_1" / feed / f"emr_facility_1_{feed}_F1.ndjson").read_bytes().decode()


def _res(out, feed):
    return [json.loads(line) for line in _lines(out, feed).splitlines()]


def _truth(out, t):
    return [json.loads(line) for line in (out / "ground_truth" / f"{t}.jsonl").read_text().splitlines()]


def test_files_format_and_tags(out):
    for feed in FEEDS:
        text = _lines(out, feed)
        assert text.endswith("\n") and text
        res = [json.loads(line) for line in text.splitlines()]
        assert [r["id"] for r in res] == sorted(r["id"] for r in res)
        for line, r in zip(text.splitlines(), res):
            assert list(r)[:3] == ["resourceType", "id", "meta"]
            assert r["resourceType"] == feed.capitalize()
            assert r["meta"]["tag"] == [{"system": "urn:synthetic-data", "code": TOKEN}]
            assert line == json.dumps(r, separators=(",", ":"))
        assert TOKEN.encode() in text.encode()[:4096]


def test_references_resolve(out):
    ids = {f.capitalize(): {r["id"] for r in _res(out, f)} for f in FEEDS[:3]}
    enc = _res(out, "encounter")
    assert len(enc) == CI["records_per_file"]
    for e in enc:
        refs = [e["subject"]["reference"], e["serviceProvider"]["reference"]]
        refs += [p["individual"]["reference"] for p in e["participant"]]
        for ref in refs:
            kind, rid = ref.split("/")
            assert rid in ids[kind]
        assert e["class"]["code"] in ("AMB", "IMP")
        assert e["identifier"][0]["value"] == e["id"]
    for f in ("practitioner", "organization"):
        for r in _res(out, f):
            assert r["identifier"][0]["system"] == "http://hl7.org/fhir/sid/us-npi"


def test_no_claim_ids_and_encounter_link(out):
    ec = _truth(out, "encounter_claim")
    claim_ids = {r["claim_id"] for r in ec}
    for f in out.rglob("*.837"):
        claim_ids |= set(re.findall(r"CLM\*([^*]+)", f.read_text()))
        claim_ids |= set(re.findall(r"REF\*F8\*([^~*]+)", f.read_text()))
    text = "".join(_lines(out, f) for f in FEEDS)
    assert '"claim_id"' not in text
    for cid in claim_ids:
        assert cid not in text
    by_enc = {r["encounter_id"] for r in ec}
    for e in _res(out, "encounter"):
        assert e["id"] in by_enc


def test_patient_truth_matches_837_member(out):
    truth = _truth(out, "person_truth")
    emr = {r["source_record_id"]: r["person_truth"] for r in truth if r["source"] == "emr_facility_1"}
    payer = {r["source_record_id"]: r["person_truth"] for r in truth if r["source"] == "payer_a"}
    patients = _res(out, "patient")
    assert patients and {p["id"] for p in patients} == set(emr)
    for p in patients:
        assert p["identifier"][0] == {"system": "urn:emr-facility-1:mrn", "value": p["id"]}
        assert emr[p["id"]] and "PA" + p["id"][3:] in payer
        assert payer["PA" + p["id"][3:]] == emr[p["id"]]


def test_manifest_era_and_determinism(out, tmp_path):
    m = json.loads((out / "manifest.json").read_text())
    emr = [f for f in m["files"] if f["source"] == "emr_facility_1"]
    assert len(emr) == 4 and all(f["era"] == "F1" for f in emr)
    other = _run(tmp_path / "out")

    def digest(root):
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob("*")) if p.is_file()}  # fmt: skip

    assert digest(out) == digest(other)


def test_encounter_class_period_and_originals_only(out):
    ec: dict[str, set] = {}
    for r in _truth(out, "encounter_claim"):
        ec.setdefault(r["encounter_id"], set()).add(r["claim_id"])
    text = {f.name: f.read_text() for f in out.rglob("*.837")}
    freq = {}
    for t in text.values():
        for cid, f in re.findall(r"CLM\*([^*]+)\*[^*]*\*\*\*[^:]*:[AB]:(\d)", t):
            freq[cid] = f
    kinds = set()
    enc = _res(out, "encounter")
    assert len({e["id"] for e in enc}) == len(enc)  # a sampled 7/8 version would duplicate its original's id
    for e in enc:
        assert "1" in {freq[c] for c in ec[e["id"]]}  # derived from the original version
        kind = e["id"][3]
        kinds.add(kind)
        if kind == "I":
            assert e["class"]["code"] == "IMP" and e["period"]["end"] >= e["period"]["start"]
        else:
            assert kind == "P" and e["class"]["code"] == "AMB" and set(e["period"]) == {"start"}
    assert kinds == {"P", "I"}


def test_encounter_subject_is_claim_member(out):
    """Each Encounter's subject Patient is the same person as the NM1*IL member of its claims."""
    truth = {(r["source"], r["source_record_id"]): r["person_truth"] for r in _truth(out, "person_truth")}
    member = {}
    for f in out.rglob("*.837"):
        current = None
        for seg in (s.strip() for s in f.read_text().split("~")):
            if seg.startswith("NM1*IL*"):
                current = seg.split("*")[9]
            elif seg.startswith("CLM*"):
                member[seg.split("*")[1]] = current
    claims: dict[str, set] = {}
    for r in _truth(out, "encounter_claim"):
        claims.setdefault(r["encounter_id"], set()).add(r["claim_id"])
    for e in _res(out, "encounter"):
        person = truth[("emr_facility_1", e["subject"]["reference"].split("/")[1])]
        assert claims[e["id"]]
        for cid in claims[e["id"]]:
            assert truth[("payer_a", member[cid])] == person
