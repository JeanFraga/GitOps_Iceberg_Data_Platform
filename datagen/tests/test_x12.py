import hashlib
import json
import re

import pytest

from datagen import config, x12
from datagen.generate import Context, generate
from datagen.npi import is_valid_npi

TOKEN = config.marker_token()
CI = {"records_per_file": 300, "years": 1}


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    root = tmp_path_factory.mktemp("x12") / "out"
    generate(Context(20261008, "ci", CI, TOKEN), root)
    return root


def _files(out):
    files = sorted(out.rglob("*.837"))
    assert len(files) == 6
    return files


def _claims(segs):
    """Yield (CLM segment, segments of that claim until the next HL)."""
    cur = None
    for s in segs:
        if s[0] == "CLM":
            cur = [s]
        elif s[0] in ("HL", "SE") and cur:
            yield cur[0], cur
            cur = None
        elif cur is not None:
            cur.append(s)


def test_envelopes_and_counts(out):
    for path in _files(out):
        data = path.read_bytes()
        assert data.startswith(b"ISA") and data.index(b"~") == 105
        segs = x12.parse(data)
        isa, gs, ge, iea = segs[0], segs[1], segs[-2], segs[-1]
        assert [s[0] for s in (isa, gs, ge, iea)] == ["ISA", "GS", "GE", "IEA"]
        assert iea == ["IEA", "1", isa[13]] and ge[2] == gs[6]
        sts = [i for i, s in enumerate(segs) if s[0] == "ST"]
        assert int(ge[1]) == len(sts)
        for i in sts:
            se = next(j for j in range(i, len(segs)) if segs[j][0] == "SE")
            assert int(segs[se][1]) == se - i + 1 and segs[se][2] == segs[i][2]
            assert segs[i + 1][:4] == ["BHT", "0019", "00", TOKEN]
            assert sum(s[0] == "CLM" for s in segs[i:se]) <= x12.MAX_PER_ST
        assert TOKEN.encode() in data[:4096]


def test_npis_versions_and_codes(out):
    for path in _files(out):
        segs = x12.parse(path.read_bytes())
        npis = [s[9] for s in segs if s[0] == "NM1" and len(s) > 9 and s[8] == "XX"]
        assert npis and all(is_valid_npi(n) for n in npis)
        seen, freqs = set(), set()
        for clm, claim in _claims(segs):
            freq = clm[5].split(":")[2]
            freqs.add(freq)
            refs = [s[2] for s in claim if s[:2] == ["REF", "F8"]]
            if freq == "1":
                assert not refs
            else:
                assert refs and refs[0] in seen
            seen.add(clm[1])
        assert freqs == {"1", "7", "8"}
        for s in segs:
            if s[0] == "SV1":
                code = s[1].split(":")[1]
                assert re.fullmatch(r"\d{5}|[A-V]\d{4}", code)
            if s[0] == "SV3":
                assert re.fullmatch(r"AD:D\d{4}", s[1])


def test_837i_institutional_elements(out):
    for path in out.rglob("payer_a_837i_*.837"):
        n = 0
        for clm, claim in _claims(x12.parse(path.read_bytes())):
            n += 1
            assert re.fullmatch(r"\d{2}:A:[178]", clm[5])
            ids = {tuple(s[:2]) for s in claim}
            assert {("DTP", "435"), ("DTP", "096")} <= ids
            assert any(s[0] == "SV2" and re.fullmatch(r"\d{4}", s[1]) for s in claim)
            assert any(s[0] == "HI" and re.fullmatch(r"DR:\d{3}", s[1]) for s in claim)
        assert n == CI["records_per_file"]


def test_manifest_eras_and_truth(out):
    m = json.loads((out / "manifest.json").read_text())
    x = [f for f in m["files"] if f["path"].endswith(".837")]
    assert len(x) == 6
    for feed in ("837p", "837i", "837d"):
        assert sorted(f["era"] for f in x if f["feed"] == feed) == ["A1", "A2"]
    assert all("era" not in f for f in m["files"] if f["source"] == "payer_b")
    claims = [json.loads(line) for line in (out / "ground_truth" / "encounter_claim.jsonl").read_text().splitlines()]
    assert len(claims) == sum(f["records"] for f in x)
    truth = [json.loads(line) for line in (out / "ground_truth" / "person_truth.jsonl").read_text().splitlines()]
    pa = [r["source_record_id"] for r in truth if r.get("source") == "payer_a"]
    assert pa and len(pa) == len(set(pa))


def test_deterministic_837(tmp_path):
    hashes = []
    for name in ("a", "b"):
        generate(Context(7, "ci", CI, TOKEN), tmp_path / name)
        hashes.append({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path / name).rglob("*.837")})
    assert hashes[0] == hashes[1] and len(hashes[0]) == 6


def test_parse_rejects_non_x12():
    with pytest.raises(ValueError):
        x12.parse(b"GS*HC~")


def test_multi_st_envelopes(tmp_path):
    from datagen.feeds import payer_a_837p

    data = payer_a_837p.FEED.generate(Context(3, "big", {"records_per_file": 1200, "years": 1}, TOKEN)).files[0].content
    segs = x12.parse(data)
    assert int(segs[-2][1]) > 1
    sts = [i for i, s in enumerate(segs) if s[0] == "ST"]
    assert len(sts) == int(segs[-2][1])
    for i in sts:
        se = next(j for j in range(i, len(segs)) if segs[j][0] == "SE")
        assert segs[se][2] == segs[i][2] and int(segs[se][1]) == se - i + 1
        assert sum(s[0] == "CLM" for s in segs[i:se]) <= x12.MAX_PER_ST


def test_837i_dates_within_era(out):
    for path in out.rglob("payer_a_837i_*.837"):
        segs = x12.parse(path.read_bytes())
        file_date = segs[1][4]
        hi = "20240630" if path.stem.endswith("A1") else "20241231"
        for s in segs:
            if s[:3] == ["DTP", "434", "RD8"]:
                end = s[3].split("-")[1]
                assert end <= hi and end <= file_date
