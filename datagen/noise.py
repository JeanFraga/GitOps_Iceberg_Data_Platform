"""FR-4 identity noise: pluggable scenarios applied deterministically per identity record.

`view(ctx, source, record_id, person, address)` decides, from an RNG seeded by
`{seed}:noise:{source}:{record_id}`, whether the record is noisy (probability q = 1 - sqrt(1 - rate), so the
share of within-person record pairs with at least one noisy side is about `rate`) and which applicable,
enabled scenario applies. The result is cached so every feed writing the same record writes the same identity."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from datagen import population
from datagen.population import Address, Person


class ScenarioError(ValueError):
    """A configured scenario name is not in the registry."""


@dataclass(frozen=True)
class Identity:
    first_name: str
    last_name: str
    dob: date
    sex: str
    address: Address | None
    ssn: str
    noise_type: str | None = None


def ssn(person_id: str) -> str:
    """Deterministic 9-digit pseudo-SSN, area starting 9 (never issued), no dashes."""
    digits = int(hashlib.sha256(f"ssn:{person_id}".encode()).hexdigest(), 16) % 10**8
    return f"9{digits:08d}"


NICKNAMES = {
    "Alice": "Ali",
    "Elena": "Ellie",
    "Olivia": "Liv",
    "Sofia": "Sophie",
    "Isla": "Izzy",
    "Lucia": "Lucy",
    "Nadia": "Nadi",
    "Gabriel": "Gabe",
    "Samuel": "Sam",
    "Nikhil": "Nik",
    "Rafael": "Rafa",
    "Tomas": "Tom",
    "Mateo": "Matt",
    "Victor": "Vic",
    "Xavier": "Xavi",
    "Jonas": "Jon",
    "Darius": "Dar",
}

ADDRESS_SOURCES = frozenset({"payer_b", "emr_facility_1"})
SSN_SOURCES = ADDRESS_SOURCES


@dataclass(frozen=True)
class Scenario:
    applies: Callable[[str, Identity], bool]
    apply: Callable[[random.Random, Identity, tuple[Address, ...]], Identity]


def _always(source: str, i: Identity) -> bool:
    return True


def _addr_source(source: str, i: Identity) -> bool:
    return source in ADDRESS_SOURCES and i.address is not None


def _ssn_source(source: str, i: Identity) -> bool:
    return source in SSN_SOURCES


def _age(i: Identity) -> int:
    ref, d = population.REFERENCE_DATE, i.dob
    return ref.year - d.year - ((ref.month, ref.day) < (d.month, d.day))


def _typo(rng: random.Random, i: Identity, pool) -> Identity:
    field = rng.choice(("first_name", "last_name"))
    name = getattr(i, field)
    pos = rng.randrange(len(name))
    letters = [c for c in "abcdefghijklmnopqrstuvwxyz" if c != name[pos].lower()]
    ch = rng.choice(letters)
    ch = ch.upper() if name[pos].isupper() else ch
    return replace(i, **{field: name[:pos] + ch + name[pos + 1 :]})


def _other_last(rng: random.Random, last: str) -> str:
    return rng.choice([n for n in population.LAST if n != last])


def _moved(rng: random.Random, a: Address) -> Address:
    line = f"{rng.randint(10, 9999)} {rng.choice(population.STREETS)} {rng.choice(population.SUFFIXES)}"
    if line == a.line1:
        line = "1 " + line
    city, state, zip3 = rng.choice(population.CITIES)
    return Address(line, city, state, f"{zip3}{rng.randint(0, 99):02d}")


def _dob_swap(rng, i: Identity, pool) -> Identity:
    return replace(i, dob=date(i.dob.year, i.dob.day, i.dob.month))


def _twin(rng, i: Identity, pool) -> Identity:
    names = population.FIRST_F if i.sex == "F" else population.FIRST_M
    return replace(i, first_name=rng.choice([n for n in names if n != i.first_name]))


def _shared_household(rng, i: Identity, pool) -> Identity:
    return replace(i, address=rng.choice([a for a in pool if a != i.address]))


def _cross_payer(rng, i: Identity, pool) -> Identity:
    return replace(i, address=_moved(rng, i.address), last_name=_other_last(rng, i.last_name))


SCENARIOS: dict[str, Scenario] = {
    "typo": Scenario(_always, _typo),
    "nickname": Scenario(
        lambda s, i: i.first_name in NICKNAMES, lambda r, i, p: replace(i, first_name=NICKNAMES[i.first_name])
    ),
    "name_swap": Scenario(
        lambda s, i: i.first_name != i.last_name,
        lambda r, i, p: replace(i, first_name=i.last_name, last_name=i.first_name),
    ),
    "hyphenated_surname": Scenario(
        lambda s, i: _age(i) >= 18, lambda r, i, p: replace(i, last_name=f"{i.last_name}-{_other_last(r, i.last_name)}")
    ),
    "dob_day_month_swap": Scenario(lambda s, i: i.dob.day <= 12 and i.dob.day != i.dob.month, _dob_swap),
    "twin": Scenario(_always, _twin),
    "move": Scenario(_addr_source, lambda r, i, p: replace(i, address=_moved(r, i.address))),
    "ssn_missing": Scenario(_ssn_source, lambda r, i, p: replace(i, ssn="")),
    "ssn_last4": Scenario(_ssn_source, lambda r, i, p: replace(i, ssn=i.ssn[-4:])),
    "ssn_default": Scenario(_ssn_source, lambda r, i, p: replace(i, ssn="999999999")),
    "surname_change": Scenario(
        lambda s, i: _age(i) >= 18, lambda r, i, p: replace(i, last_name=_other_last(r, i.last_name))
    ),
    "newborn_placeholder": Scenario(
        lambda s, i: _age(i) < 1, lambda r, i, p: replace(i, first_name="BABY BOY" if i.sex == "M" else "BABY GIRL")
    ),
    "jr_sr": Scenario(
        lambda s, i: i.sex == "M", lambda r, i, p: replace(i, last_name=f"{i.last_name} {r.choice(('JR', 'SR'))}")
    ),
    "shared_household": Scenario(_addr_source, _shared_household),
    "cross_payer_switch": Scenario(lambda s, i: s == "payer_b" and i.address is not None, _cross_payer),
}


def scenario_set(exclude: list[str] | tuple[str, ...] = ()) -> tuple[str, ...]:
    unknown = sorted(set(exclude) - set(SCENARIOS))
    if unknown:
        raise ScenarioError(f"unknown noise scenario(s): {', '.join(unknown)}")
    return tuple(n for n in SCENARIOS if n not in exclude)


def decide(ctx, source: str, record_id: str, clean: Identity, pool: tuple[Address, ...]) -> Identity:
    rng = random.Random(f"{ctx.seed}:noise:{source}:{record_id}")
    q = 1 - math.sqrt(1 - ctx.edge_case_rate)
    if rng.random() >= q:
        return clean
    names = [n for n in SCENARIOS if n in ctx.scenarios and SCENARIOS[n].applies(source, clean)]
    if not names:
        return clean
    name = rng.choice(names)
    return replace(SCENARIOS[name].apply(rng, clean, pool), noise_type=name)


def _pool(ctx) -> tuple[Address, ...]:
    if "noise_pool" not in ctx.cache:
        hhs = ctx.population(ctx.volume["records_per_file"])
        ctx.cache["noise_pool"] = tuple(dict.fromkeys(hh.address for hh in hhs))
    return ctx.cache["noise_pool"]


def view(ctx, source: str, record_id: str, person: Person, address: Address | None) -> Identity:
    views = ctx.cache.setdefault("noise_views", {})
    key = (source, record_id)
    if key not in views:
        clean = Identity(person.first_name, person.last_name, person.dob, person.sex, address, ssn(person.person_id))
        ident = decide(ctx, source, record_id, clean, _pool(ctx))
        views[key] = ident
        if ident.noise_type:
            ctx.cache.setdefault("noise_names", set()).add(f"{ident.first_name} {ident.last_name}")
    return views[key]
