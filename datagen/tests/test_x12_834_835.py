import hashlib
import json
from datetime import date, timedelta

import pytest

from datagen import config, registry, x12
from datagen.generate import BASE_YEAR, Context, generate

TOKEN = config.marker_token()
CI = {"records_per_file": 300, "years": 1}


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    root = tmp_path_factory.mktemp("x834") / "out"
    generate(Context(20261008, "ci", CI, TOKEN), root)
    return root


def _d(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))


def _members(segs):
    """Yield the segments of each INS loop."""
    cur = None
    for s in segs:
        if s[0] == "INS":
            if cur:
                yield cur
            cur = [s]
        elif s[0] == "SE":
            if cur:
                yield cur
            cur = None
        elif cur is not None:
            cur.append(s)


def _clps(segs):
    cur = None
    for s in segs:
        if s[0] in ("LX", "SE"):
            if cur:
                yield cur
            cur = None
        if s[0] == "CLP":
            cur = [s]
        elif cur is not None and s[0] != "LX":
            cur.append(s)


def test_envelopes(out):
    files = sorted(out.rglob("*.834")) + sorted(out.rglob("*.835"))
    assert len(list(out.rglob("*.835"))) == 6
    for path in files:
        data = path.read_bytes()
        assert data.startswith(b"ISA") and data.index(b"~") == 105
        assert TOKEN.encode() in data[:4096]
        segs = x12.parse(data)
        isa, gs, ge, iea = segs[0], segs[1], segs[-2], segs[-1]
        assert iea == ["IEA", "1", isa[13]] and ge[2] == gs[6]
        set_id, ver, fid = ("834", "005010X220A1", "BE") if path.suffix == ".834" else ("835", "005010X221A1", "HP")
        assert gs[1] == fid and gs[8] == ver
        sts = [i for i, s in enumerate(segs) if s[0] == "ST"]
        assert int(ge[1]) == len(sts)
        for i in sts:
            assert segs[i][1] == set_id and segs[i][3] == ver
            se = next(j for j in range(i, len(segs)) if segs[j][0] == "SE")
            assert int(segs[se][1]) == se - i + 1 and segs[se][2] == segs[i][2]
            unit = "INS" if set_id == "834" else "CLP"
            assert sum(s[0] == unit for s in segs[i:se]) <= x12.MAX_PER_ST
            if set_id == "834":
                assert segs[i + 1][:3] == ["BGN", "00", TOKEN]
            else:
                assert segs[i + 2][0] == "TRN" and segs[i + 3] == ["REF", "EV", TOKEN]


def test_834_spans_match_truth(out):
    files = sorted(out.rglob("*.834"), key=lambda p: ("change" in p.name, p.name))
    assert "full" in files[0].name and len(files) >= 2
    assert [x12.parse(f.read_bytes())[3][8] for f in files[:2]] == ["RX", "2"]
    codes, open_, spans = set(), {}, []
    for f in files:
        for m in _members(x12.parse(f.read_bytes())):
            code, mid = m[0][3], m[1][2]
            codes.add(code)
            hd = next((s for s in m if s[0] == "HD"), None)
            if code == "001":
                assert hd is None
            elif code == "021":
                assert mid not in open_
                open_[mid] = (hd[4], next(s[3] for s in m if s[:2] == ["DTP", "348"]))
            else:
                plan, start = open_.pop(mid)
                assert hd[4] == plan
                spans.append((mid, plan, start, next(s[3] for s in m if s[:2] == ["DTP", "349"])))
    spans += [(mid, plan, start, f"{BASE_YEAR + CI['years'] - 1}1231") for mid, (plan, start) in open_.items()]
    assert codes == {"021", "024", "001"}
    derived = sorted((m, p, f"{s[:4]}-{s[4:6]}-{s[6:]}", f"{e[:4]}-{e[4:6]}-{e[6:]}") for m, p, s, e in spans)
    rows = [json.loads(line) for line in (out / "ground_truth" / "coverage_spans.jsonl").read_text().splitlines()]
    truth = sorted(
        (r["source_record_id"], r["plan_id"], r["coverage_start"], r["coverage_end"])
        for r in rows
        if r.get("source") == "payer_a"
    )
    assert derived == truth
    by: dict[str, list] = {}
    for m, _, s, e in truth:
        by.setdefault(m, []).append((s, e))
    gaps = [
        v
        for v in by.values()
        if len(v) == 2 and date.fromisoformat(v[1][0]) > date.fromisoformat(v[0][1]) + timedelta(days=1)
    ]
    assert gaps


def test_835_claims(out):
    clm = {}
    for p in out.rglob("*.837"):
        for s in x12.parse(p.read_bytes()):
            if s[0] == "CLM":
                clm[s[1]] = s
    seen, voids, n_clp = {}, 0, 0
    for path in out.rglob("*.835"):
        segs = x12.parse(path.read_bytes())
        for clp in _clps(segs):
            c = clp[0]
            assert c[1] in clm and float(c[3]) == float(clm[c[1]][2]) * (-1 if c[2] == "22" else 1)
            amt = [s for s in clp if s[:2] == ["AMT", "AU"]]
            pr = [s for s in clp if s[:2] == ["CAS", "PR"]]
            assert amt and pr and pr[0][3] == c[5]
            assert round(float(amt[0][2]) - float(c[5]), 2) == float(c[4])
            seen[c[1]] = c
            n_clp += 1
            if c[9] == "8":
                voids += 1
                assert c[2] == "22" and float(c[3]) < 0
        assert segs[1][4] == max(s[2] for s in segs if s[:2] == ["DTM", "405"])
    assert voids and set(seen) == set(clm) and n_clp == len(clm)


def test_void_negates_original(out):
    refs = {}
    for p in out.rglob("*.837"):
        cur = None
        for s in x12.parse(p.read_bytes()):
            if s[0] == "CLM":
                cur = s[1]
            elif s[:2] == ["REF", "F8"] and cur:
                refs[cur] = s[2]
    clps = {}
    for p in out.rglob("*.835"):
        for clp in _clps(x12.parse(p.read_bytes())):
            clps[clp[0][1]] = clp[0]
    voids = [c for c in clps.values() if c[9] == "8"]
    assert voids
    for v in voids:
        o = clps[refs[v[1]]]
        assert [float(x) for x in v[3:6]] == [-float(x) for x in o[3:6]]


def test_deterministic_and_837_unchanged(tmp_path):
    def run(name, feeds=None):
        generate(Context(7, "ci", CI, TOKEN), tmp_path / name, feeds)
        root = tmp_path / name
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    a, b = run("a"), run("b")
    assert a == b
    only = run("c", [f for f in registry.discover() if f.feed.startswith("837")])
    assert {k: v for k, v in a.items() if k.endswith(".837")} == {k: v for k, v in only.items() if k.endswith(".837")}
