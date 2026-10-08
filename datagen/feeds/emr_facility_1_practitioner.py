"""EMR Facility 1 FHIR R4 Practitioner NDJSON (era F1)."""

from __future__ import annotations

from datagen import fhir
from datagen.registry import Feed

FEED = Feed(fhir.SOURCE, "practitioner", lambda ctx: fhir.build(ctx)["practitioner"])
