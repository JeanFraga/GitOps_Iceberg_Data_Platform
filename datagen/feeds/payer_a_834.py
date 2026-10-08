"""Payer A 834 enrollment (X12 005010X220A1): one full file plus monthly change files.

INS03 021 opens a coverage span, 024 closes it, 001 is a non-coverage address change.
Shape follows the guide loosely; not certified against it."""

from __future__ import annotations

import random
from datetime import date, timedelta

from datagen import noise, x12
from datagen.claims837 import RECEIVER, SOURCE, _d8, payer_a_member_id
from datagen.registry import DataFile, Feed, FeedOutput

FEED_NAME = "834"
VERSION = "005010X220A1"
SENDER = "PAYERAENR"
PLANS = ("PAHMO01", "PAPPO02", "PAEPO03")
STREETS = ("OAK", "MAPLE", "CEDAR", "PINE", "ELM", "BIRCH")


def _month(first: date, i: int) -> date:
    return date(first.year + i // 12, i % 12 + 1, 1)


def _month_end(first: date, i: int) -> date:
    return _month(first, i + 1) - timedelta(days=1)


def _timeline(rng: random.Random, months: int) -> tuple[list[tuple[int, str, int | None]], int | None]:
    """Spans as (start month, plan, end month or None) and an optional address-change month."""
    start = 0 if rng.random() < 0.75 else rng.randint(1, min(11, months - 1))
    plan = rng.choice(PLANS)
    roll = rng.random()
    spans: list[tuple[int, str, int | None]]
    if roll < 0.20 and start <= months - 4:
        end = rng.randint(start, months - 4)
        new_start = min(end + 1 + rng.randint(1, 3), months - 1)
        spans = [(start, plan, end), (new_start, rng.choice([p for p in PLANS if p != plan]), None)]
    elif 0.20 <= roll < 0.30 and start <= months - 2:
        spans = [(start, plan, rng.randint(start, months - 2))]
    else:
        spans = [(start, plan, None)]
    first_end = spans[0][2] if spans[0][2] is not None else months - 1
    move = rng.randint(start + 1, first_end) if rng.random() < 0.15 and first_end > start else None
    return spans, move


def generate(ctx) -> FeedOutput:
    rng = random.Random(f"{ctx.seed}:{SOURCE}:{FEED_NAME}")
    n = ctx.volume["records_per_file"]
    first = date(ctx.years[0], 1, 1)
    last = date(ctx.years[-1], 12, 31)
    months = 12 * len(ctx.years)
    out = FeedOutput()
    # events[month] -> (sort date, member id, seq, member segments); month -1 is the full file.
    events: dict[int, list[tuple[date, str, int, list[str]]]] = {}
    s = x12.segment
    count = 0
    for hh in ctx.population(n):
        if count + len(hh.members) > n:
            break  # whole households only
        count += len(hh.members)
        for p in hh.members:
            mid = payer_a_member_id(p)
            v = noise.view(ctx, SOURCE, mid, p, None)
            out.person_truth.append(
                {"source": SOURCE, "source_record_id": mid, "person_truth": p.person_id, "noise_type": v.noise_type}
            )
            spans, move = _timeline(rng, months)
            addr = (hh.address.line1, hh.address.city, hh.address.state, hh.address.zip)
            new_addr = (
                f"{rng.randint(100, 9999)} {rng.choice(STREETS)} ST",
                hh.address.city,
                hh.address.state,
                f"{(int(hh.address.zip) + rng.randint(1, 99)) % 100000:05d}",
            )

            def member(code: str, reason: str, at: tuple, tail: list[str], p=v, mid=mid) -> list[str]:
                return [
                    s("INS", "Y", "18", code, reason, "A", "", "", "FT"),
                    s("REF", "0F", mid),
                    s("NM1", "IL", "1", p.last_name, p.first_name, "", "", "", "ZZ", mid),
                    s("N3", at[0]),
                    s("N4", at[1], at[2], at[3]),
                    s("DMG", "D8", _d8(p.dob), p.sex),
                    *tail,
                ]

            for seq, (sm, plan, em) in enumerate(spans):
                cur = new_addr if move is not None and sm >= move else addr
                begin = _month(first, sm)
                key = -1 if sm == 0 else sm
                hd = [s("HD", "021", "", "HLT", plan, "EMP"), s("DTP", "348", "D8", _d8(begin))]
                events.setdefault(key, []).append((begin, mid, seq * 3, member("021", "28", cur, hd)))
                end = _month_end(first, em) if em is not None else last
                if em is not None:
                    at = new_addr if move is not None and em >= move else addr
                    hd = [s("HD", "024", "", "HLT", plan, "EMP"), s("DTP", "349", "D8", _d8(end))]
                    events.setdefault(em, []).append((end, mid, seq * 3 + 2, member("024", "07", at, hd)))
                out.coverage_spans.append(
                    {
                        "source": SOURCE,
                        "source_record_id": mid,
                        "plan_id": plan,
                        "coverage_start": begin.isoformat(),
                        "coverage_end": end.isoformat(),
                    }
                )
            if move is not None:
                when = _month(first, move)
                tail = [s("DTP", "303", "D8", _d8(when))]
                events.setdefault(move, []).append((when, mid, 1, member("001", "43", new_addr, tail)))
    for key in sorted(events):
        rows = sorted(events[key], key=lambda e: e[:3])
        if key == -1:
            fdate, action, name = first, "RX", f"payer_a_834_full_{_d8(first)}.834"
        else:
            fdate, action = _month_end(first, key), "2"
            name = f"payer_a_834_change_{_d8(fdate)[:6]}.834"
        ic = x12.Interchange(SENDER, RECEIVER, _d8(fdate), "1200", VERSION, functional_id="BE", set_id="834")
        for start in range(0, len(rows), x12.MAX_PER_ST):
            body = [
                s("BGN", "00", ctx.token, _d8(fdate), "1200", "", "", "", action),
                s("N1", "P5", "PAYER A EMPLOYER GROUP", "FI", "999999999"),
                s("N1", "IN", "PAYER A", "XV", RECEIVER),
            ]
            for row in rows[start : start + x12.MAX_PER_ST]:
                body += row[3]
            ic.add(body)
        out.files.append(DataFile(name, ic.render(), len(rows)))
    return out


FEED = Feed(SOURCE, FEED_NAME, generate)
