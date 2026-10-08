"""Payer A 837I claims (X12 005010X223A2), one file per era."""

from __future__ import annotations

from datagen import claims837
from datagen.registry import Feed


def generate(ctx):
    return claims837.build(ctx, "I")


FEED = Feed(claims837.SOURCE, "837i", generate)
