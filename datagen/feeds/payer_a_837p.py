"""Payer A 837P claims (X12 005010X222A1), one file per era."""

from __future__ import annotations

from datagen import claims837
from datagen.registry import Feed


def generate(ctx):
    return claims837.build(ctx, "P")


FEED = Feed(claims837.SOURCE, "837p", generate)
