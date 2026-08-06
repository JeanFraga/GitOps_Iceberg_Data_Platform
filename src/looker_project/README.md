# LookML project — NYC Taxi Gold

Semantic layer over the Gold star schema in BigQuery
(`gold_star_schema`), built by `src/dbt_project`.

## Layout

There is no single Looker-mandated folder structure — the only hard rule
is that `manifest.lkml` sits at the project root. This layout follows the
widely-used convention (models / views / explores / dashboards) plus the
`model_includes/` pattern from Google's modular-LookML guidance.

```
src/looker_project/
├── manifest.lkml                  # project name + environment constants
├── model_includes/                # shared, model-level config
│   ├── datagroups.lkml            # cache policy (24h, keyed to the daily load)
│   └── named_value_formats.lkml   # $ / mi / min / mph formats
├── models/
│   └── nyc_taxi.model.lkml        # connection, includes, week start, persist_with
├── explores/
│   └── trips.explore.lkml         # the star schema joined together
├── views/
│   ├── fact_trips.view.lkml       # fact grain, dimensions + measures
│   ├── dim_date.view.lkml         # calendar dimension
│   └── dim_locations.view.lkml    # TLC zone dimension (joined twice)
└── dashboards/
    └── trip_overview.dashboard.lookml
```

File extensions are the officially supported set: `.model.lkml`,
`.view.lkml`, `.explore.lkml`, `.dashboard.lookml`, and plain `.lkml`
for includes and refinements.

### Why explores live outside the model

Explores are usually written inline in the model file. Splitting them out
costs one `include:` and buys the ability to add a second model — a
departmental or embed-scoped one — that reuses or refines the same
Explore rather than copy-pasting it.

### Why `model_includes/` holds only datagroups and formats

Model-level parameters that must bind to *this* model (`connection`,
`week_start_day`, `fiscal_month_offset`, `persist_with`) stay in the
model file where their scope is unambiguous. Only genuinely shareable
objects are factored out.

## Mapping to the Gold layer

| LookML view | dbt model | Grain |
|---|---|---|
| `fact_trips` | `models/gold/fact_trips.sql` | one row per trip |
| `dim_date` | `models/gold/dim_date.sql` | one row per calendar date |
| `dim_locations` | `models/gold/dim_locations.sql` | one row per TLC zone |

`dim_locations` is joined twice (pickup and dropoff) using `from:`, which
is why the view itself carries no pickup/dropoff wording — the Explore's
`view_label` supplies it.

Types mirror the physical BigQuery schema. Notably `ratecode_id` and all
amount columns are `FLOAT64` (not `INT64`), and the pickup/dropoff
columns are `TIMESTAMP`, which is why the `dimension_group`s declare
`datatype: timestamp` and the rate-code `CASE` compares float literals.

## Connecting Looker to this project

Three things are configured outside LookML and must be done by hand:

1. **BigQuery connection** — Admin → Database → Connections. Name it
   `nyc_taxi_bigquery` to match `constant: connection_name` in
   `manifest.lkml`, or change the constant. Use a service account with
   `roles/bigquery.dataViewer` on `gold_star_schema` and
   `roles/bigquery.jobUser` on the project.
2. **Git connection** — Looker binds a project to a Git repo and treats
   that repo's root as the project root, so `manifest.lkml` must be at
   the root of whatever repo Looker is pointed at. This directory is
   nested inside the platform monorepo, so either mirror it out to a
   dedicated LookML repo, or point Looker at a repo whose root is this
   folder's contents. See "Deploying" below.
3. **OAuth client** — required by the Terraform resource; see
   `infra/modules/looker/README-prereqs.md`.

## Deploying out of the monorepo

Keeping LookML beside the dbt models that produce the tables is what
makes a change to `fact_trips.sql` and its `fact_trips.view.lkml`
reviewable in one PR. The cost is that Looker cannot consume a
subdirectory directly. The usual bridge is a CI job that mirrors this
folder to the root of a dedicated LookML repo on merge to `main` — the
same shape as `.github/workflows/composer-sync.yml`, which syncs
`src/composer/dags` to the Composer DAG bucket.

That workflow is **not** included here; add it once you have decided
whether Looker will point at a mirrored repo or a standalone one.

## Validating changes

LookML has no offline compiler — validation happens in the Looker IDE
(**Validate LookML**) or via the Looker API. There is therefore no
`make` target for this project; a syntax error surfaces on the first
push to the connected repo.
