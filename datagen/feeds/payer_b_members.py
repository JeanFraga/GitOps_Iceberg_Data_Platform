"""Payer B flat member CSV: one file per coverage year, same members every year."""

from __future__ import annotations

import csv
import io
import random

from datagen import noise
from datagen.npi import generate_npi
from datagen.registry import DataFile, Feed, FeedOutput

SOURCE, FEED_NAME = "payer_b", "members"
COLUMNS = [
    "member_id",
    "subscriber_id",
    "person_code",
    "household_id",
    "first_name",
    "last_name",
    "dob",
    "sex",
    "address_line1",
    "city",
    "state",
    "zip",
    "pcp_npi",
    "coverage_start",
    "coverage_end",
    "ssn",
]


def generate(ctx) -> FeedOutput:
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{FEED_NAME}")
    n = ctx.volume["records_per_file"]
    pcps = [generate_npi(rng) for _ in range(max(1, n // 200))]
    members = []
    for i, hh in enumerate(ctx.population(n)):
        if len(members) + len(hh.members) > n:
            break  # never emit a partial household
        subscriber_id = f"PB{i + 1:08d}"
        dependents_from = 2 if hh.has_spouse else 1
        for j, p in enumerate(hh.members):
            # 01 subscriber, 02 only the actual spouse, 03+ dependents in order.
            code = f"{j + 1 if j < dependents_from else j - dependents_from + 3:02d}"
            member_id = f"{subscriber_id}-{code}"
            v = noise.view(ctx, SOURCE, member_id, p, hh.address)
            members.append(
                {
                    "member_id": member_id,
                    "subscriber_id": subscriber_id,
                    "person_code": code,
                    "household_id": hh.household_id,
                    "first_name": v.first_name,
                    "last_name": v.last_name,
                    "dob": v.dob.isoformat(),
                    "sex": v.sex,
                    "address_line1": v.address.line1,
                    "city": v.address.city,
                    "state": v.address.state,
                    "zip": v.address.zip,
                    "pcp_npi": rng.choice(pcps),
                    "ssn": v.ssn,
                    "_person_id": p.person_id,
                    "_noise": v.noise_type,
                    "_start_month": rng.choice((1, 1, 1, 1, 2, 4, 7)),
                }
            )
    members.sort(key=lambda m: (m["subscriber_id"], m["person_code"]))
    out = FeedOutput()
    for m in members:
        out.person_truth.append(
            {
                "source": SOURCE,
                "source_record_id": m["member_id"],
                "person_truth": m["_person_id"],
                "noise_type": m["_noise"],
            }
        )
    for year in ctx.years:
        buf = io.StringIO()
        buf.write(f"# {ctx.token}\n")
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(COLUMNS)
        for m in members:
            # First year honours a mid-year enrolment; later years cover the full year.
            start = f"{year}-{m['_start_month'] if year == ctx.years[0] else 1:02d}-01"
            end = f"{year}-12-31"
            writer.writerow([*(m[c] for c in COLUMNS[:-3]), start, end, m["ssn"]])
            out.coverage_spans.append(
                {"source": SOURCE, "source_record_id": m["member_id"], "coverage_start": start, "coverage_end": end}
            )
        out.files.append(DataFile(f"payer_b_members_{year}.csv", buf.getvalue().encode(), len(members)))
    return out


FEED = Feed(SOURCE, FEED_NAME, generate)
