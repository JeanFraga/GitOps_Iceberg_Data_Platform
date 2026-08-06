"""
Daily incremental NYC TLC load: each run ingests the next unloaded month
(bronze -> silver -> BigLake registration -> dbt gold build).

State derivation is self-healing: the next month is the successor of the
newest success marker under gs://<bucket>/state/bronze_loaded/, written only
after a Bronze batch completes. Physical data files are deliberately NOT
used as state — Iceberg writes files before the metadata commit, so failed
batches (and pre-existing stray partitions) would otherwise fake progress.
Missed days, retries, and manual reruns all converge on the first month that
is genuinely missing; with no markers at all the DAG starts from DATA_START
(an idempotent re-load if CI already ingested it). Once caught up with TLC's
publication lag the run skips cleanly until new data appears.

Runtime configuration (GCP_PROJECT_ID, GCP_REGION) comes from environment
variables set on the Composer environment by infra/modules/composer. Job
files under gs://<bucket>/jobs/ are uploaded by .github/workflows/release.yml
on every deploy; this DAG intentionally reuses them and their argument
contract rather than duplicating the Spark code path.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime, timedelta

import requests
from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocCreateBatchOperator,
)

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
REGION = os.environ.get("GCP_REGION", "us-east1")

# Bucket name must match infra/modules/bq_iceberg's iceberg_warehouse bucket
# (same convention as src/spark_jobs/common.py and release.yml).
BUCKET = f"{PROJECT_ID}-iceberg-warehouse"
WAREHOUSE = f"gs://{BUCKET}/warehouse"
# Success markers written after each committed Bronze load (the DAG's state).
STATE_PREFIX = "state/bronze_loaded/"

# Must match the values pinned in .github/workflows/release.yml.
DATAPROC_RUNTIME_VERSION = "2.2"
ICEBERG_SPARK_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.13:1.5.2"
# Must match infra/modules/bq_iceberg (bq_connection_id / silver_dataset_id).
BQ_CONNECTION_ID = "iceberg-gcs-conn"
SILVER_DATASET = "silver"

DATA_START = "2023-01"  # first month to load into an empty warehouse
TLC_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{period}.parquet"

# Jinja-templated at task runtime from resolve_next_period's XCom.
XCOM_SOURCE_URI = "{{ ti.xcom_pull(task_ids='resolve_next_period')['source_uri'] }}"
XCOM_PERIOD = "{{ ti.xcom_pull(task_ids='resolve_next_period')['period'] }}"


def _pyspark_batch(job_file: str, args: list[str]) -> dict:
    """Batch spec mirroring the gcloud flags used in release.yml."""
    return {
        "pyspark_batch": {
            "main_python_file_uri": f"gs://{BUCKET}/jobs/{job_file}",
            "python_file_uris": [f"gs://{BUCKET}/jobs/common.py"],
            "args": args,
        },
        "runtime_config": {
            "version": DATAPROC_RUNTIME_VERSION,
            "properties": {
                "spark.jars.packages": ICEBERG_SPARK_PACKAGE,
                "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            },
        },
    }


@dag(
    dag_id="nyc_taxi_incremental",
    description="Load one new TLC month per day through bronze/silver/gold",
    schedule="0 6 * * *",
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    default_args={
        "owner": "data-platform",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["nyc-taxi", "incremental", "poc"],
)
def nyc_taxi_incremental():
    @task
    def resolve_next_period() -> dict:
        """Next month = successor of the newest bronze_loaded success marker."""
        hook = GCSHook()
        blobs = hook.list(BUCKET, prefix=STATE_PREFIX) or []
        months = sorted(
            {
                m.group(1)
                for blob in blobs
                if (m := re.fullmatch(rf"{re.escape(STATE_PREFIX)}(\d{{4}}-\d{{2}})", blob))
            }
        )
        if months:
            newest = datetime.strptime(months[-1], "%Y-%m")
            nxt = (newest.replace(day=1) + timedelta(days=32)).replace(day=1)
            period = nxt.strftime("%Y-%m")
        else:
            period = DATA_START
        logger.info("Newest loaded month: %s -> loading %s", months[-1] if months else None, period)

        url = TLC_URL.format(period=period)
        resp = requests.head(url, timeout=30)
        if resp.status_code in (403, 404):
            # Cloudfront answers 403 for missing keys; both mean "not published".
            raise AirflowSkipException(
                f"TLC file for {period} not published yet (HTTP {resp.status_code}); caught up."
            )
        resp.raise_for_status()  # anything else is a real error, not "caught up"
        return {
            "period": period,
            "url": url,
            "object": f"landing/yellow_tripdata_{period}.parquet",
            "source_uri": f"gs://{BUCKET}/landing/yellow_tripdata_{period}.parquet",
        }

    @task
    def stage_to_landing(resolved: dict) -> str:
        """Copy the public TLC parquet to the landing prefix on GCS.

        Downloaded in chunks to a worker temp file (~50-120 MB, well within
        the SMALL preset's storage), then uploaded — never held in memory.
        """
        with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
            with requests.get(resolved["url"], stream=True, timeout=600) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    tmp.write(chunk)
            tmp.flush()
            GCSHook().upload(bucket_name=BUCKET, object_name=resolved["object"], filename=tmp.name)
        logger.info("Staged %s", resolved["source_uri"])
        return resolved["source_uri"]

    # Deterministic per-run batch ids: an Airflow retry hits AlreadyExists and
    # the operator reattaches to the running batch instead of duplicating it.
    ingest_bronze = DataprocCreateBatchOperator(
        task_id="ingest_bronze",
        project_id=PROJECT_ID,
        region=REGION,
        batch_id="ingest-bronze-{{ ts_nodash | lower }}",
        batch=_pyspark_batch(
            "ingest_bronze.py",
            [
                f"--project-id={PROJECT_ID}",
                f"--warehouse={WAREHOUSE}",
                f"--source-uri={XCOM_SOURCE_URI}",
                f"--period={XCOM_PERIOD}",
            ],
        ),
    )

    @task
    def mark_bronze_loaded(resolved: dict) -> None:
        """Commit the DAG's high-watermark only after a successful Bronze batch."""
        GCSHook().upload(
            bucket_name=BUCKET,
            object_name=f"{STATE_PREFIX}{resolved['period']}",
            data=b"",
        )

    bronze_to_silver = DataprocCreateBatchOperator(
        task_id="bronze_to_silver",
        project_id=PROJECT_ID,
        region=REGION,
        batch_id="bronze-to-silver-{{ ts_nodash | lower }}",
        batch=_pyspark_batch(
            "bronze_to_silver.py",
            [f"--project-id={PROJECT_ID}", f"--warehouse={WAREHOUSE}"],
        ),
    )

    @task
    def register_silver() -> None:
        """Point the BigLake external table at the current Iceberg metadata
        (same DDL as the Register step in release.yml)."""
        from google.cloud import bigquery

        hook = GCSHook()
        version = (
            hook.download(
                bucket_name=BUCKET,
                object_name="warehouse/silver/yellow_trips/metadata/version-hint.text",
            )
            .decode()
            .strip()
        )
        metadata_uri = f"{WAREHOUSE}/silver/yellow_trips/metadata/v{version}.metadata.json"
        logger.info("Registering Iceberg metadata: %s", metadata_uri)

        client = bigquery.Client(project=PROJECT_ID, location=REGION)
        client.query(
            f"""
            CREATE SCHEMA IF NOT EXISTS `{PROJECT_ID}.{SILVER_DATASET}`;
            CREATE OR REPLACE EXTERNAL TABLE `{PROJECT_ID}.{SILVER_DATASET}.yellow_trips`
            WITH CONNECTION `{PROJECT_ID}.{REGION}.{BQ_CONNECTION_ID}`
            OPTIONS (format = 'ICEBERG', uris = ['{metadata_uri}'])
            """
        ).result()

    # dbt project is synced to gs://<composer-bucket>/data/dbt_project by
    # .github/workflows/composer-sync.yml and appears on workers under
    # /home/airflow/gcs/data. Copied off the GCS fuse mount so dbt's target/
    # writes stay local; dbt-bigquery itself is installed in the Composer
    # image via pypi_packages (see infra/modules/composer) — a per-run venv
    # would not fit the SMALL preset's worker storage.
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="""
        set -euo pipefail
        WORKDIR=$(mktemp -d)
        trap 'rm -rf "${WORKDIR}"' EXIT
        cp -r /home/airflow/gcs/data/dbt_project "${WORKDIR}/dbt_project"
        cd "${WORKDIR}/dbt_project"
        dbt build --profiles-dir .
        """,
    )

    resolved = resolve_next_period()
    staged = stage_to_landing(resolved)
    marked = mark_bronze_loaded(resolved)
    staged >> ingest_bronze >> marked >> bronze_to_silver >> register_silver() >> dbt_build


nyc_taxi_incremental()
