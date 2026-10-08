"""Payer A 837D claims (X12 005010X224A2), one file per era."""

from __future__ import annotations

from datagen import claims837
from datagen.registry import Feed


def generate(ctx):
    return claims837.build(ctx, "D")


FEED = Feed(claims837.SOURCE, "837d", generate)
