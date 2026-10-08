"""Pluggable feed registry (FR-1): every module in datagen/feeds/ exposing FEED is a feed."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from datagen import feeds as feeds_pkg


@dataclass(frozen=True)
class DataFile:
    name: str
    content: bytes
    records: int
    era: str | None = None


@dataclass
class FeedOutput:
    files: list[DataFile] = field(default_factory=list)
    person_truth: list[dict] = field(default_factory=list)
    coverage_spans: list[dict] = field(default_factory=list)
    encounter_claim: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Feed:
    source: str
    feed: str
    generate: Callable[[Any], FeedOutput]


def discover() -> list[Feed]:
    """Feeds in deterministic order by module name."""
    found = []
    for info in sorted(pkgutil.iter_modules(feeds_pkg.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{feeds_pkg.__name__}.{info.name}")
        if isinstance(getattr(module, "FEED", None), Feed):
            found.append(module.FEED)
    return found
