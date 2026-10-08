"""EMR Facility 1 FHIR R4 NDJSON (Patient, Practitioner, Organization, Encounter), era F1.

Stdlib only; shape loosely follows FHIR R4, not certified against US Core. Encounters are derived from
a deterministic sample of original 837P/837I claims and reuse the 837 encounter_id; no claim id is emitted."""

from __future__ import annotations

import json
import random

from datagen import claims837
from datagen.registry import DataFile, FeedOutput

SOURCE = "emr_facility_1"
ERA = "F1"
NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"
MRN_SYSTEM = "urn:emr-facility-1:mrn"
VISIT_SYSTEM = "urn:emr-facility-1:visit"
ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
FEEDS = ("patient", "practitioner", "organization", "encounter")


def mrn(person_id: str) -> str:
    return "F1M" + "".join(ch for ch in person_id if ch.isdigit())


def build(ctx) -> dict[str, FeedOutput]:
    if "fhir" not in ctx.cache:
        ctx.cache["fhir"] = _generate(ctx)
    return ctx.cache["fhir"]


def _resource(rtype: str, rid: str, token: str, **body) -> dict:
    return {
        "resourceType": rtype,
        "id": rid,
        "meta": {"tag": [{"system": "urn:synthetic-data", "code": token}]},
        **body,
    }


def _ndjson(resources: list[dict]) -> bytes:
    rows = sorted(resources, key=lambda r: r["id"])
    return "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows).encode()


def _generate(ctx) -> dict[str, FeedOutput]:
    rng = random.Random(f"{ctx.seed}:emr_facility_1:fhir")
    n = ctx.volume["records_per_file"]
    eligible = [f for kind in ("P", "I") for f in claims837.claims(ctx, kind) if f["freq"] == "1"]
    sample = sorted(rng.sample(eligible, min(n, len(eligible))), key=lambda f: f["encounter_id"])
    address = {p.person_id: hh.address for hh in ctx.population(n) for p in hh.members}
    tok = ctx.token
    patients: dict[str, dict] = {}
    practitioners: dict[str, dict] = {}
    orgs: dict[str, dict] = {}
    encounters: list[dict] = []
    person_of: dict[str, str] = {}
    for f in sample:
        person = f["person"]
        pid = mrn(person.person_id)
        person_of[pid] = person.person_id
        if pid not in patients:
            a = address[person.person_id]
            patients[pid] = _resource(
                "Patient", pid, tok,
                identifier=[{"system": MRN_SYSTEM, "value": pid}],
                name=[{"family": person.last_name, "given": [person.first_name]}],
                gender="male" if person.sex == "M" else "female",
                birthDate=person.dob.isoformat(),
                address=[{"line": [a.line1], "city": a.city, "state": a.state, "postalCode": a.zip}],
            )  # fmt: skip
        npi, idx = f["other"]
        prid = f"PR{npi}"
        role = "ATTENDING" if f["kind"] == "I" else "RENDERING"
        practitioners.setdefault(prid, _resource(
            "Practitioner", prid, tok,
            identifier=[{"system": NPI_SYSTEM, "value": npi}],
            name=[{"family": role, "given": [f"{role[0]}{idx}"]}],
        ))  # fmt: skip
        bnpi, bidx, _ = f["billing"]
        oid = f"ORG{bnpi}"
        orgs.setdefault(oid, _resource(
            "Organization", oid, tok,
            identifier=[{"system": NPI_SYSTEM, "value": bnpi}],
            name=f"PAYER A NETWORK PROVIDER {bidx}",
        ))  # fmt: skip
        inpatient = f["kind"] == "I"
        period = {"start": f["svc"].isoformat()}
        if inpatient:
            period["end"] = f["latest"].isoformat()
        encounters.append(_resource(
            "Encounter", f["encounter_id"], tok,
            status="finished",
            **{"class": {"system": ACT_CODE, "code": "IMP" if inpatient else "AMB"}},
            subject={"reference": f"Patient/{pid}"},
            participant=[{"individual": {"reference": f"Practitioner/{prid}"}}],
            period=period,
            serviceProvider={"reference": f"Organization/{oid}"},
            identifier=[{"system": VISIT_SYSTEM, "value": f["encounter_id"]}],
        ))  # fmt: skip
    out: dict[str, FeedOutput] = {}
    for feed, res in zip(
        FEEDS, (list(patients.values()), list(practitioners.values()), list(orgs.values()), encounters)
    ):
        out[feed] = FeedOutput(files=[DataFile(f"{SOURCE}_{feed}_{ERA}.ndjson", _ndjson(res), len(res), era=ERA)])
    out["patient"].person_truth = [
        {"source": SOURCE, "source_record_id": k, "person_truth": v} for k, v in sorted(person_of.items())
    ]
    return out
