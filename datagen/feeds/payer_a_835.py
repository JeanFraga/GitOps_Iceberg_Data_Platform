"""Payer A 835 remittance (X12 005010X221A1): adjudicates every 837 claim at claim level.

Claims come from the cached 837 builder, never re-randomised. Not certified against the guide."""

from __future__ import annotations

import random
from datetime import timedelta

from datagen import claims837, noise, x12
from datagen.claims837 import ERAS, RECEIVER, SOURCE, _d8
from datagen.registry import DataFile, Feed, FeedOutput

FEED_NAME = "835"
VERSION = "005010X221A1"


def _adjudicate(rng: random.Random, facts: list[dict]) -> list[dict]:
    done: dict[str, dict] = {}
    out = []
    for c in facts:
        if c["freq"] == "8":
            o = done[c["original_id"]]
            r = {k: -o[k] for k in ("charge", "allowed", "pr", "paid")}
            r.update(status="22", pr_code=o["pr_code"])
        else:
            charge = c["charge"]
            allowed = round(charge * rng.uniform(0.55, 0.95), 2)
            pr = round(allowed * rng.uniform(0.0, 0.3), 2)
            r = {"charge": charge, "allowed": allowed, "pr": pr, "paid": round(allowed - pr, 2),
                 "status": "1", "pr_code": rng.choice(("1", "2"))}  # fmt: skip
        r["claim"] = c
        done[c["claim_id"]] = r
        out.append(r)
    return out


def generate(ctx) -> FeedOutput:
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{FEED_NAME}")
    out = FeedOutput()
    s = x12.segment
    icn = 0
    for kind in ("P", "I", "D"):
        facts = claims837.claims(ctx, kind)
        for era in ERAS:
            rows = _adjudicate(rng, [c for c in facts if c["era"] == era.name])
            pay = max(r["claim"]["latest"] for r in rows) + timedelta(days=14)
            icn += 1
            ic = x12.Interchange(RECEIVER, era.sender, _d8(pay), "1200", VERSION, control=icn,
                                 functional_id="HP", set_id="835")  # fmt: skip
            by_npi: dict[tuple, list[dict]] = {}
            for r in rows:
                by_npi.setdefault(r["claim"]["billing"], []).append(r)
            for billing in sorted(by_npi):
                group = by_npi[billing]
                for start in range(0, len(group), x12.MAX_PER_ST):
                    chunk = group[start : start + x12.MAX_PER_ST]
                    total = round(sum(r["paid"] for r in chunk), 2)
                    check = f"PA{kind}{era.name}{len(ic.transactions) + 1:06d}"
                    body = [
                        s(
                            "BPR",
                            "I",
                            f"{abs(total):.2f}",
                            "C" if total >= 0 else "D",
                            "ACH",
                            "CCP",
                            "01",
                            "999999999",
                            "DA",
                            "000123456",
                            "9999999999",
                            "",
                            "01",
                            "999988880",
                            "DA",
                            "000098765",
                            _d8(pay),
                        ),
                        s("TRN", "1", check, "1999999999"),
                        s("REF", "EV", ctx.token),
                        s("DTM", "405", _d8(pay)),
                        s("N1", "PR", "PAYER A"),
                        s("N3", "1 PAYER PLAZA"),
                        s("N4", "SPRINGFIELD", "IL", "62701"),
                        s("N1", "PE", f"PAYER A NETWORK PROVIDER {billing[1]}", "XX", billing[0]),
                        s("REF", "TJ", billing[2]),
                    ]
                    for i, r in enumerate(chunk, 1):
                        c = r["claim"]
                        p = noise.view(ctx, SOURCE, c["member_id"], c["person"], None)
                        co = round(r["charge"] - r["allowed"], 2)
                        body += [
                            s("LX", str(i)),
                            s(
                                "CLP",
                                c["claim_id"],
                                r["status"],
                                f"{r['charge']:.2f}",
                                f"{r['paid']:.2f}",
                                f"{r['pr']:.2f}",
                                "12",
                                f"PA835{c['claim_id']}",
                                "11",
                                c["freq"],
                            ),
                        ]
                        if co > 0 or (r["status"] == "22" and co < 0):
                            body.append(s("CAS", "CO", "45", f"{co:.2f}"))
                        body += [
                            s("CAS", "PR", r["pr_code"], f"{r['pr']:.2f}"),
                            s("NM1", "QC", "1", p.last_name, p.first_name, "", "", "", "MI", c["member_id"]),
                            s("AMT", "AU", f"{r['allowed']:.2f}"),
                        ]
                    ic.add(body)
            out.files.append(
                DataFile(f"payer_a_835_{kind.lower()}_{era.name}.835", ic.render(), len(rows), era=era.name)
            )
    return out


FEED = Feed(SOURCE, FEED_NAME, generate)
