"""Seeded shared population: persons grouped into households. Stdlib random only."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

# Reference date for ages; fixed so output never depends on the wall clock.
REFERENCE_DATE = date(2025, 1, 1)

FIRST_F = [
    "Alice",
    "Amara",
    "Beatriz",
    "Carmen",
    "Chloe",
    "Dana",
    "Elena",
    "Fatima",
    "Grace",
    "Hana",
    "Ingrid",
    "Isla",
    "Jade",
    "Keiko",
    "Lena",
    "Lucia",
    "Maya",
    "Mei",
    "Nadia",
    "Nora",
    "Olivia",
    "Priya",
    "Quinn",
    "Rosa",
    "Sofia",
    "Tamar",
    "Uma",
    "Vera",
    "Wren",
    "Yara",
    "Zoe",
]
FIRST_M = [
    "Aarav",
    "Ben",
    "Carlos",
    "Darius",
    "Eli",
    "Felix",
    "Gabriel",
    "Hugo",
    "Ivan",
    "Jamal",
    "Jonas",
    "Kenji",
    "Leo",
    "Luca",
    "Malik",
    "Mateo",
    "Nikhil",
    "Omar",
    "Oscar",
    "Pablo",
    "Rafael",
    "Samuel",
    "Theo",
    "Tomas",
    "Umar",
    "Victor",
    "Wes",
    "Xavier",
    "Yusuf",
    "Zane",
]
LAST = [
    "Abara",
    "Bellweather",
    "Castellan",
    "Draycott",
    "Eskildsen",
    "Farrowby",
    "Galvanek",
    "Holloway",
    "Ivarsen",
    "Juniper",
    "Kestrel",
    "Lindqvist",
    "Marchetti",
    "Nakashima",
    "Okonkwo",
    "Pendergast",
    "Quillon",
    "Ravensby",
    "Saltonstall",
    "Thornquist",
    "Underhill",
    "Valcourt",
    "Whitlock",
    "Yarrow",
    "Zelenko",
    "Ashgrove",
    "Brightwater",
    "Coldridge",
    "Dunmore",
    "Emberly",
    "Fairhaven",
    "Greywood",
]
STREETS = [
    "Maple",
    "Oak",
    "Cedar",
    "Birch",
    "Willow",
    "Elm",
    "Aspen",
    "Juniper",
    "Spruce",
    "Hawthorn",
    "Linden",
    "Poplar",
]
SUFFIXES = ["St", "Ave", "Rd", "Ln", "Ct", "Way", "Dr"]
CITIES = (
    ("Springfield", "IL", "627"),
    ("Riverton", "WY", "825"),
    ("Fairview", "TN", "370"),
    ("Greenville", "SC", "296"),
)


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    state: str
    zip: str


@dataclass(frozen=True)
class Person:
    person_id: str
    first_name: str
    last_name: str
    sex: str
    dob: date


@dataclass(frozen=True)
class Household:
    household_id: str
    address: Address
    members: tuple[Person, ...]  # [0] subscriber, [1] spouse if has_spouse, then dependents
    has_spouse: bool = False


def _dob(rng: random.Random, min_age: int, max_age: int) -> date:
    return REFERENCE_DATE - timedelta(days=rng.randint(min_age * 365, max_age * 365 + 364))


def build(seed: int, persons: int) -> list[Household]:
    """At least `persons` persons in households, deterministic for a seed."""
    rng = random.Random(seed)
    households: list[Household] = []
    count = 0
    while count < persons:
        h = len(households) + 1
        last = rng.choice(LAST)
        city, state, zip3 = rng.choice(CITIES)
        address = Address(
            f"{rng.randint(10, 9999)} {rng.choice(STREETS)} {rng.choice(SUFFIXES)}",
            city,
            state,
            f"{zip3}{rng.randint(0, 99):02d}",
        )
        members = []

        def person(min_age: int, max_age: int, sex: str | None = None, last: str = last) -> Person:
            nonlocal count
            count += 1
            sex = sex or rng.choice("FM")
            first = rng.choice(FIRST_F if sex == "F" else FIRST_M)
            return Person(f"P{count:08d}", first, last, sex, _dob(rng, min_age, max_age))

        subscriber = person(24, 70)
        members.append(subscriber)
        has_spouse = rng.random() < 0.55
        if has_spouse:
            members.append(person(24, 70, "M" if subscriber.sex == "F" else "F"))
        for _ in range(rng.choice((0, 0, 1, 1, 2, 3))):
            members.append(person(0, 23))
        households.append(Household(f"H{h:08d}", address, tuple(members), has_spouse))
    return households
