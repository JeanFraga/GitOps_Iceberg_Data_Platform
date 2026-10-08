"""Shared Payer A 837 claim builder (P/I/D): two eras, original/replacement/void versions.

Shape follows X12 005010 X222A1 / X223A2 / X224A2 loosely; not certified against the guides.
CPT/CDT values are random code-shaped strings, never real descriptors."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from datagen import x12
from datagen.npi import generate_npi
from datagen.population import Person
from datagen.registry import DataFile, FeedOutput

SOURCE = "payer_a"
RECEIVER = "PAYERA"
ERA_BOUNDARY = date(2024, 7, 1)


@dataclass(frozen=True)
class Era:
    name: str
    sender: str
    claim_prefix: str


ERAS = (Era("A1", "PAYERACH1", "A1"), Era("A2", "PAYERACH2", "AX"))
VERSIONS = {"P": "005010X222A1", "I": "005010X223A2", "D": "005010X224A2"}

# Real code values (no descriptors) for diagnosis and HCPCS Level II.
ICD10 = ["E119", "I10", "J069", "M545", "R51", "K219", "E785", "F419", "J45909", "N390", "Z0000", "R0602",
         "M1990", "L309", "H6590", "K5900", "R1084", "G4700", "J0190", "B349"]  # fmt: skip
HCPCS = ["G0008", "G0438", "G0439", "J1100", "J3420", "A4253", "E0607", "G0121", "Q2035", "J7613"]
REVENUE = ["0250", "0260", "0300", "0320", "0360", "0450", "0636", "0730", "0110", "0120"]
BILL_TYPES = ["11", "13", "12", "14", "83", "85"]
POS = ["11", "22", "02", "19"]


def payer_a_member_id(person: Person) -> str:
    return "PA" + "".join(ch for ch in person.person_id if ch.isdigit())


def era_range(name: str, years: list[int]) -> tuple[date, date]:
    end = date(years[-1], 12, 31)
    return (date(years[0], 1, 1), ERA_BOUNDARY - timedelta(days=1)) if name == "A1" else (ERA_BOUNDARY, end)


def cpt(rng: random.Random) -> str:
    return f"{rng.randrange(10000, 100000)}"


def cdt(rng: random.Random) -> str:
    return f"D{rng.randrange(10000):04d}"


def _d8(d: date) -> str:
    return d.strftime("%Y%m%d")


def _claim(rng, kind, claim_id, freq, original_id, person, member_id, billing, other, svc, lines, amt, hi):
    """Billing provider HL, subscriber HL and the 2300 claim loop; returns (segments, latest date)."""
    s = x12.segment
    seg = [
        s("NM1", "85", "2", f"PAYER A NETWORK PROVIDER {billing[1]}", "", "", "", "", "XX", billing[0]),
        s("N3", "100 SYNTHETIC WAY"),
        s("N4", "SPRINGFIELD", "IL", "62701"),
        s("REF", "EI", billing[2]),
        "",  # placeholder for HL pair inserted by caller
        s("SBR", "P", "18", "", "", "", "", "", "", "CI"),
        s("NM1", "IL", "1", person.last_name, person.first_name, "", "", "", "MI", member_id),
        s("DMG", "D8", _d8(person.dob), person.sex),
        s("NM1", "PR", "2", "PAYER A", "", "", "", "", "PI", RECEIVER),
    ]
    facility = rng.choice(BILL_TYPES) if kind == "I" else rng.choice(POS)
    qual = "A" if kind == "I" else "B"
    seg.append(
        s("CLM", claim_id, f"{amt:.2f}", "", "", f"{facility}:{qual}:{freq}", "" if kind == "I" else "Y", "A", "Y", "Y")
    )
    end = svc
    if kind == "I":
        start, end = svc, min(hi, svc + timedelta(days=rng.randint(0, 6)))
        seg += [
            s("DTP", "434", "RD8", f"{_d8(start)}-{_d8(end)}"),
            s("DTP", "435", "DT", f"{_d8(start)}{rng.randint(0, 23):02d}00"),
            s("DTP", "096", "TM", f"{rng.randint(6, 20):02d}00"),
            s("CL1", "1", "7", "01"),
        ]
    if freq != "1":
        seg.append(s("REF", "F8", original_id))
    if kind != "D":
        dx = rng.sample(ICD10, 2)
        seg.append(s("HI", f"ABK:{dx[0]}", f"ABF:{dx[1]}"))
    if kind == "I":
        seg.append(s("HI", f"DR:{rng.randint(1, 999):03d}"))
        seg.append(s("NM1", "71", "1", "ATTENDING", f"A{other[1]}", "", "", "", "XX", other[0]))
    else:
        seg.append(s("NM1", "82", "1", "RENDERING", f"R{other[1]}", "", "", "", "XX", other[0]))
    for i, (code, line_amt) in enumerate(lines, 1):
        seg.append(s("LX", str(i)))
        if kind == "P":
            seg.append(s("SV1", f"HC:{code}", f"{line_amt:.2f}", "UN", "1", "", "", "1"))
        elif kind == "I":
            seg.append(s("SV2", rng.choice(REVENUE), f"HC:{code}", f"{line_amt:.2f}", "UN", "1"))
        else:
            seg.append(s("SV3", f"AD:{code}", f"{line_amt:.2f}", "", "", "", "1"))
            seg.append(s("TOO", "JP", str(rng.randint(1, 32))))
        seg.append(s("DTP", "472", "D8", _d8(svc)))
    return seg, end


def build(ctx, kind: str) -> FeedOutput:
    feed = f"837{kind.lower()}"
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{feed}")
    n = ctx.volume["records_per_file"]
    persons = [p for hh in ctx.population(n) for p in hh.members]
    billing = [(generate_npi(rng), f"{i + 1:04d}", f"{rng.randrange(10**8, 10**9)}") for i in range(max(2, n // 100))]
    others = [(generate_npi(rng), f"{i + 1:04d}") for i in range(max(3, n // 50))]
    out = FeedOutput()
    members: dict[str, str] = {}
    for era in ERAS:
        lo, hi = era_range(era.name, ctx.years)
        span = (hi - lo).days
        txs: list[tuple[date, list[str]]] = []
        pending: list[tuple[int, dict]] = []
        seq = 0
        while len(txs) < n:
            due = next((p for p in pending if p[0] <= len(txs)), None)
            if due:
                pending.remove(due)
                c = due[1]
            else:
                seq += 1
                person = rng.choice(persons)
                code_fn = cdt if kind == "D" else (lambda r: r.choice(HCPCS) if r.random() < 0.2 else cpt(r))
                lines = [(code_fn(rng), round(rng.uniform(40, 900), 2)) for _ in range(rng.randint(1, 4))]
                c = {
                    "encounter_id": f"E{era.name}{kind}{seq:08d}",
                    "person": person,
                    "billing": rng.choice(billing),
                    "other": rng.choice(others),
                    "svc": lo + timedelta(days=rng.randint(0, span)),
                    "lines": lines,
                    "freq": "1",
                    "original": None,
                }
                roll = rng.random()
                if roll >= 0.85:
                    follow = dict(c, freq="7" if roll < 0.95 else "8")
                    if follow["freq"] == "7":
                        follow["lines"] = [(code, round(a * 1.1, 2)) for code, a in lines]
                    pending.append((len(txs) + 1 + rng.randint(0, 20), follow))
            c_id = f"{era.claim_prefix}{kind}{len(txs) + 1:09d}"
            if c["freq"] == "1":
                for p in pending:
                    if p[1]["encounter_id"] == c["encounter_id"]:
                        p[1]["original"] = c_id
            member_id = payer_a_member_id(c["person"])
            members[member_id] = c["person"].person_id
            amt = sum(a for _, a in c["lines"])
            body, latest = _claim(rng, kind, c_id, c["freq"], c["original"], c["person"], member_id,
                          c["billing"], c["other"], c["svc"], c["lines"], amt, hi)  # fmt: skip
            txs.append((latest, body))
            out.encounter_claim.append({"encounter_id": c["encounter_id"], "claim_source": feed, "claim_id": c_id})
        last = max(d for d, _ in txs)
        ic = x12.Interchange(era.sender, RECEIVER, _d8(last), "1200", VERSIONS[kind])
        for start in range(0, len(txs), x12.MAX_PER_ST):
            body = [
                x12.segment("BHT", "0019", "00", ctx.token, _d8(last), "1200", "CH"),
                x12.segment("NM1", "41", "2", "PAYER A CLEARINGHOUSE", "", "", "", "", "46", era.sender),
                x12.segment("PER", "IC", "EDI DESK", "TE", "5555550100"),
                x12.segment("NM1", "40", "2", "PAYER A", "", "", "", "", "46", RECEIVER),
            ]
            hl = 0
            for _, claim in txs[start : start + x12.MAX_PER_ST]:
                hl += 2
                hls = [
                    x12.segment("HL", str(hl - 1), "", "20", "1"),
                    x12.segment("HL", str(hl), str(hl - 1), "22", "0"),
                ]
                body += [hls[0], *claim[:4], hls[1], *claim[5:]]
            ic.add(body)
        out.files.append(DataFile(f"payer_a_837{kind.lower()}_{era.name}.837", ic.render(), len(txs), era=era.name))
    out.person_truth = [
        {"source": SOURCE, "source_record_id": m, "person_truth": pid} for m, pid in sorted(members.items())
    ]
    return out
