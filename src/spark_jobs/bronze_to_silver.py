"""
Bronze → Silver PySpark ETL for NYC Taxi Yellow Trip data.

Runs on Dataproc Serverless via .github/workflows/release.yml, which supplies
the Iceberg runtime coordinate (ICEBERG_SPARK_PACKAGE) and ships common.py via
--py-files. Local runs additionally need a GCS connector jar for gs:// access
(pip PySpark ships none) — see the README Quick-Start for the exact command.

Performs:
  1. Read Bronze Iceberg table
  2. Cleanse / filter / de-duplicate on MERGE_KEYS
  3. MERGE INTO Silver Iceberg table (idempotent upsert)
  4. Iceberg table maintenance (compaction + snapshot expiration)
"""

import argparse
import logging
import sys
from functools import reduce

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col

from common import (
    BRONZE_TABLE,
    CATALOG,
    SILVER_TABLE,
    TRIP_COLUMNS,
    build_spark_session,
    default_warehouse_uri,
)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Business key of a trip. Drives both de-duplication and the MERGE ON clause so
# the two can never drift apart; transform output is unique on exactly this key.
# vendor_id + a second-granularity pickup alone is NOT unique across ~3M
# trips/month, so the key includes dropoff and both zone IDs to avoid
# collapsing distinct simultaneous trips.
MERGE_KEYS = (
    "vendor_id",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "pu_location_id",
    "do_location_id",
)

# Catalog-relative table name for Iceberg maintenance procedures.
_SILVER_TABLE_IN_CATALOG = SILVER_TABLE.split(".", 1)[1]


def ensure_silver_table(spark: SparkSession) -> None:
    """Create the Silver table (canonical trip schema) if it does not exist."""
    columns_ddl = ",\n            ".join(f"{name} {dtype}" for name, dtype in TRIP_COLUMNS)
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.silver")
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {SILVER_TABLE} (
            {columns_ddl}
        )
        USING iceberg
        PARTITIONED BY (days(tpep_pickup_datetime))
        """
    )


def transform_bronze_to_silver(bronze_df: DataFrame) -> DataFrame:
    """Apply Silver-layer filtering and de-duplication rules.

    Rows missing any MERGE_KEYS component are dropped: a NULL key component
    never matches in MERGE ON, so such rows would duplicate on every re-run.
    """
    keys_present = reduce(lambda a, b: a & b, [col(k).isNotNull() for k in MERGE_KEYS])
    return bronze_df.filter(
        (col("trip_distance") > 0)
        & (col("total_amount") > 0)
        & (col("passenger_count").isNotNull())
        & keys_present
    ).dropDuplicates(list(MERGE_KEYS))


def merge_into_silver(spark: SparkSession, silver_df: DataFrame) -> None:
    """Idempotently upsert ``silver_df`` into the Silver table on MERGE_KEYS."""
    silver_df.createOrReplaceTempView("silver_updates")
    on_clause = " AND ".join(f"t.{k} = s.{k}" for k in MERGE_KEYS)
    spark.sql(
        f"""
        MERGE INTO {SILVER_TABLE} t
        USING silver_updates s
        ON {on_clause}
        WHEN MATCHED THEN
            UPDATE SET *
        WHEN NOT MATCHED THEN
            INSERT *
        """
    )


def run_maintenance(spark: SparkSession, retain_snapshots: int) -> None:
    """Compact data files and expire old snapshots on the Silver table."""
    logger.info("Running compaction (rewrite_data_files) …")
    spark.sql(
        f"CALL {CATALOG}.system.rewrite_data_files("
        f"  table => '{_SILVER_TABLE_IN_CATALOG}',"
        f"  strategy => 'sort',"
        f"  sort_order => 'tpep_pickup_datetime ASC NULLS LAST'"
        f")"
    )

    logger.info("Expiring old snapshots (retain_last=%d) …", retain_snapshots)
    spark.sql(
        f"CALL {CATALOG}.system.expire_snapshots("
        f"  table => '{_SILVER_TABLE_IN_CATALOG}',"
        f"  retain_last => {retain_snapshots}"
        f")"
    )


def run_silver_pipeline(warehouse_uri: str, retain_snapshots: int) -> None:
    spark = build_spark_session("Bronze_to_Silver_Taxi_ETL", warehouse_uri)

    logger.info("Reading Bronze Iceberg table …")
    bronze_df = spark.read.format("iceberg").load(BRONZE_TABLE)

    logger.info("Cleaning and filtering …")
    silver_df = transform_bronze_to_silver(bronze_df)

    ensure_silver_table(spark)

    logger.info("Running MERGE INTO %s …", SILVER_TABLE)
    merge_into_silver(spark, silver_df)

    run_maintenance(spark, retain_snapshots)

    logger.info("Pipeline complete.")
    spark.stop()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Bronze → Silver Taxi ETL")
    parser.add_argument("--project-id", required=True, help="GCP project ID")
    parser.add_argument(
        "--warehouse",
        default=None,
        help="GCS URI for the Iceberg warehouse root (defaults to gs://<project-id>-iceberg-warehouse/warehouse)",
    )
    parser.add_argument(
        "--retain-snapshots",
        type=int,
        default=5,
        help="Number of Iceberg snapshots to retain during expiration (default: 5)",
    )
    args = parser.parse_args(argv)
    if args.retain_snapshots <= 0:
        parser.error("--retain-snapshots must be greater than 0")
    return args


if __name__ == "__main__":
    args = parse_args()
    warehouse = args.warehouse or default_warehouse_uri(args.project_id)
    run_silver_pipeline(
        warehouse_uri=warehouse,
        retain_snapshots=args.retain_snapshots,
    )
