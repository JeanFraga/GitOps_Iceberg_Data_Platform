"""EMR Facility 1 FHIR R4 Patient NDJSON (era F1)."""

from __future__ import annotations

from datagen import fhir
from datagen.registry import Feed

FEED = Feed(fhir.SOURCE, "patient", lambda ctx: fhir.build(ctx)["patient"])
