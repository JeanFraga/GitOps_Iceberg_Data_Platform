"""Provider directory reference CSV: practitioners (entity type 1) and facilities (entity type 2)."""

from __future__ import annotations

import csv
import io
import random

from datagen.npi import generate_npi
from datagen.population import CITIES, FIRST_F, FIRST_M, LAST, STREETS, SUFFIXES
from datagen.registry import DataFile, Feed, FeedOutput

SOURCE, FEED_NAME = "provider_directory", "providers"
COLUMNS = [
    "npi",
    "entity_type_code",
    "first_name",
    "last_name",
    "credential",
    "organization_name",
    "taxonomy_code",
    "address_line1",
    "city",
    "state",
    "zip",
]
PRACTITIONER_TAXONOMY = (("207Q00000X", "MD"), ("207R00000X", "MD"), ("363L00000X", "NP"), ("1223G0001X", "DDS"))
FACILITY_TAXONOMY = (("282N00000X", "General Hospital"), ("261QP2300X", "Primary Care Clinic"),
                     ("3336C0003X", "Community Pharmacy"))  # fmt: skip


def generate(ctx) -> FeedOutput:
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{FEED_NAME}")
    count = min(ctx.volume["records_per_file"], max(10, ctx.volume["records_per_file"] // 10))
    rows, seen = [], set()
    for i in range(count):
        npi = generate_npi(rng)
        while npi in seen:
            npi = generate_npi(rng)
        seen.add(npi)
        city, state, zip3 = rng.choice(CITIES)
        addr = [f"{rng.randrange(1, 9999)} {rng.choice(STREETS)} {rng.choice(SUFFIXES)}", city, state,
                f"{zip3}{rng.randrange(100):02d}"]  # fmt: skip
        if i % 4 == 3:
            tax, kind = rng.choice(FACILITY_TAXONOMY)
            rows.append([npi, "2", "", "", "", f"Synthetic {city} {kind} {i + 1:03d}", tax, *addr])
        else:
            tax, cred = rng.choice(PRACTITIONER_TAXONOMY)
            first = rng.choice(rng.choice((FIRST_F, FIRST_M)))
            rows.append([npi, "1", first, rng.choice(LAST), cred, "", tax, *addr])
    rows.sort(key=lambda r: r[0])
    buf = io.StringIO()
    buf.write(f"# {ctx.token}\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return FeedOutput(files=[DataFile("providers.csv", buf.getvalue().encode(), len(rows))])


FEED = Feed(SOURCE, FEED_NAME, generate)
