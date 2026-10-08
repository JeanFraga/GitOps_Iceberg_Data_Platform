"""Synthetic NPIs. Prefix 29 is a project-reserved convention marking NPIs as synthetic; it is not
an officially reserved range and may overlap issued numbers. The check digit follows the CMS
Luhn rule over the 80840 card-issuer prefix plus the first nine digits."""

from __future__ import annotations

import random

PREFIX = "29"


def _luhn_check_digit(body: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:  # rightmost body digit is doubled (check digit not yet appended)
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return (10 - total % 10) % 10


def generate_npi(rng: random.Random) -> str:
    first9 = PREFIX + "".join(str(rng.randrange(10)) for _ in range(7))
    return first9 + str(_luhn_check_digit("80840" + first9))


def is_valid_npi(npi: str) -> bool:
    return len(npi) == 10 and npi.isdigit() and _luhn_check_digit("80840" + npi[:9]) == int(npi[9])
