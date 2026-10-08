"""EMR Facility 1 FHIR R4 Encounter NDJSON (era F1)."""

from __future__ import annotations

from datagen import fhir
from datagen.registry import Feed

FEED = Feed(fhir.SOURCE, "encounter", lambda ctx: fhir.build(ctx)["encounter"])
