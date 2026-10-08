"""Payer A NCPDP-style flat pharmacy claims CSV: one file per year, paid claims only."""

from __future__ import annotations

import csv
import io
import random
from datetime import date, timedelta

from datagen import noise
from datagen.claims837 import RECEIVER, SOURCE, payer_a_member_id
from datagen.ndc import FORMS, generate_ndc
from datagen.npi import generate_npi
from datagen.registry import DataFile, Feed, FeedOutput

FEED_NAME = "pharmacy"
COLUMNS = [
    "payer_id",
    "rx_number",
    "fill_number",
    "service_provider_id_qualifier",
    "service_provider_id",
    "ncpdp_id",
    "prescriber_id",
    "cardholder_id",
    "patient_first_name",
    "patient_last_name",
    "patient_dob",
    "patient_gender_code",
    "date_of_service",
    "product_service_id",
    "product_name",
    "quantity_dispensed",
    "days_supply",
    "ingredient_cost_paid",
    "dispensing_fee_paid",
    "patient_pay_amount",
    "total_amount_paid",
    "transaction_response_status",
]


def _money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def generate(ctx) -> FeedOutput:
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{FEED_NAME}")
    n = ctx.volume["records_per_file"]
    persons = [p for hh in ctx.population(n) for p in hh.members]
    pharmacies = [(generate_npi(rng), f"7{rng.randrange(10**6):06d}") for _ in range(max(3, n // 50))]
    prescribers = [generate_npi(rng) for _ in range(max(3, n // 30))]
    drugs = [(generate_ndc(rng, FORMS[i % 3]), f"SYNTH DRUG {i + 1:04d}", rng.randrange(200, 30000)) for i in range(40)]
    out = FeedOutput()
    rx_seq = 0
    emitted: dict[str, str] = {}
    for year in ctx.years:
        start, days = date(year, 1, 1), (date(year, 12, 31) - date(year, 1, 1)).days
        rows: list[list] = []
        while len(rows) < n:
            p = rng.choice(persons)
            pharm_npi, ncpdp = rng.choice(pharmacies)
            prescriber = rng.choice(prescribers)
            ndc, name, unit_cents = rng.choice(drugs)
            supply = rng.choice((30, 30, 30, 90))
            qty = supply * rng.choice((1, 1, 2))
            fills = min(rng.choice((1, 1, 2, 3, 4)), n - len(rows))
            rx_seq += 1
            rx = f"{rx_seq:07d}"
            first = start + timedelta(days=rng.randrange(days + 1))
            member = payer_a_member_id(p)
            v = noise.view(ctx, SOURCE, member, p, None)
            for k in range(fills):
                dos = first + timedelta(days=k * supply)
                if dos.year != year:
                    break
                ingredient = unit_cents * qty // 30
                fee = rng.choice((150, 175, 200, 250))
                copay = min(rng.choice((0, 500, 1000, 2500)), ingredient + fee)
                total = ingredient + fee - copay
                rows.append(
                    [
                        RECEIVER, rx, k, "01", pharm_npi, ncpdp, prescriber, member,
                        v.first_name, v.last_name, v.dob.strftime("%Y%m%d"), "1" if v.sex == "M" else "2",
                        dos.strftime("%Y%m%d"), ndc, name, qty, supply,
                        _money(ingredient), _money(fee), _money(copay), _money(total), "P",
                    ]
                )  # fmt: skip
                emitted[member] = p.person_id
        rows.sort(key=lambda r: (r[12], r[1], r[2]))
        buf = io.StringIO()
        buf.write(f"# {ctx.token}\n")
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
        out.files.append(DataFile(f"payer_a_pharmacy_{year}.csv", buf.getvalue().encode(), len(rows)))
    for member, pid in sorted(emitted.items()):
        nt = ctx.cache["noise_views"][(SOURCE, member)].noise_type
        out.person_truth.append({"source": SOURCE, "source_record_id": member, "person_truth": pid, "noise_type": nt})
    return out


FEED = Feed(SOURCE, FEED_NAME, generate)
