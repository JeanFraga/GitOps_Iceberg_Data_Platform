# datagen — synthetic healthcare data generator

**All data produced by this generator is synthetic. It contains no real PHI.** Every data file
carries the marker `SYNTHETIC-DATA-NO-REAL-PHI` (checked by `make marker-check`).

## Modules

| Module | Role |
|---|---|
| `registry.py`, `feeds/` | Feed registry: one module per `<source>_<feed>`, discovered automatically |
| `population.py` | Seeded households and persons shared by all feeds |
| `noise.py` | Identity noise plugins (typos, nicknames, swaps…), edge-case rate, eval-only scenarios |
| `drift.py` | Schema drift injection (rename/add/remove column, cast failure, date format) |
| `data_drift.py` | Data drift samples (code mix, null rate, unit scale, amount shift) |
| `x12.py`, `claims837.py` | X12 834 / 835 / 837 (P, I, D) writers |
| `fhir.py` | FHIR R4 NDJSON (EMR Facility 1: patient, practitioner, organization, encounter) |
| `estimate.py` | Size and storage-cost estimate plus budget headroom for full-size runs |
| `upload.py` | Lands files in `gs://$PROJECT-landing/` and loads `mpi_eval.ground_truth` |
| `config.py` | Reads `config/resolved.yaml`, `.env` fill rule, marker token |
| `ndc.py`, `npi.py` | NDC forms (4-4-2, 5-3-2, 5-4-1) and Luhn-valid NPIs |
| `generate.py` | Deterministic writer: landing files, ground truth JSONL, `manifest.json`, `names.txt` |

## Volume profiles

`datagen.volume_profile` in config picks a profile from `datagen.volume_profiles`:

- `ci` — 5,000 records per file, 1 year; written to `datagen/out/` (git-ignored).
- `full` — 30,000 records per file, 2 years; generated outside the repo and landed in GCS.

Precedence: `VOLUME=` / `--volume` > config > `.env`. `.env` (`DATAGEN_VOLUME_PROFILE`, and the
per-field keys) only fills values config leaves unset; on conflict config wins with a warning.

## Local run

```sh
make generate               # VOLUME from config (ci) -> datagen/out/
make generate EVAL=1        # held-out eval seed, all noise scenarios
make generate-upload        # land datagen/out/ and load ground truth
```

## Full-size run

```sh
make generate VOLUME=full           # estimate -> budget guard -> generate to temp -> land
make generate VOLUME=full FORCE=1   # upload even when the estimate exceeds budget headroom
```

The estimate (files, bytes, USD/month) is printed first; if it exceeds the remaining budget the run
stops unless `FORCE=1`. Nothing is written inside the repo.

## Committed samples

`make samples` regenerates `datagen/samples/` deterministically from a sample-sized train run
(`repo_weight.sample_records` = 1,000 records per file, 1 year, same seed and drift config):
`<source>/<feed>/*`, `ground_truth/*.jsonl` and `manifest.json` (paths relative to `datagen/samples/`).
Per-feed totals vary: 837/835 write one 1,000-claim file per era (and 835 per claim type), members and
pharmacy split 1,000 records across base and drift slices, and FHIR patient, practitioner, organization and
providers are derived from the sampled claims, so they hold fewer. The generated names list is never committed. Rerunning leaves the tree unchanged.

`make repo-weight` (part of `make validate`) fails on any committed data file outside
`datagen/samples/` above `repo_weight.sample_records` records or `repo_weight.max_bytes` bytes
(`config/standards/guardrails.yaml`).
