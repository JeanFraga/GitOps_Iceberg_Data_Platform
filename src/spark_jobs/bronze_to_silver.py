"""
Bronze → Silver PySpark ETL for NYC Taxi Yellow Trip data.

Designed for Dataproc Serverless (spark-submit or gcloud dataproc batches submit).
Performs:
  1. Read Bronze Iceberg table
  2. Cleanse / filter / de-duplicate
  3. MERGE INTO Silver Iceberg table (idempotent upsert)
  4. Iceberg table maintenance (compaction + snapshot expiration)

Usage:
    spark-submit \\
      --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \\
      bronze_to_silver.py \\
      --project-id <GCP_PROJECT_ID> \\
      [--warehouse gs://<bucket>/warehouse] \\
      [--retain-snapshots 5]
"""

import argparse
import logging
import sys

from pyspark.sql import SparkSession
from pyspark.sql import DataFrame
from pyspark.sql.functions import col

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

ICEBERG_RUNTIME = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2"
GCS_CONNECTOR = "com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.20"


def build_spark_session(warehouse_uri: str) -> SparkSession:
    """Build a SparkSession configured for Iceberg on GCS."""
    return (
        SparkSession.builder.appName("Bronze_to_Silver_Taxi_ETL")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.gcs_catalog", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.gcs_catalog.type", "hadoop")
        .config("spark.sql.catalog.gcs_catalog.warehouse", warehouse_uri)
        # Enable Iceberg vectorized reads for better performance
        .config("spark.sql.iceberg.vectorization.enabled", "true")
        .getOrCreate()
    )


def ensure_silver_table(spark: SparkSession) -> None:
    """Create the Silver table if it does not already exist."""
    spark.sql("CREATE NAMESPACE IF NOT EXISTS gcs_catalog.silver")
    spark.sql(
        """
        CREATE TABLE IF NOT EXISTS gcs_catalog.silver.yellow_trips (
            vendor_id             BIGINT,
            tpep_pickup_datetime  TIMESTAMP,
            tpep_dropoff_datetime TIMESTAMP,
            passenger_count       DOUBLE,
            trip_distance         DOUBLE,
            ratecode_id           DOUBLE,
            store_and_fwd_flag    STRING,
            pu_location_id        BIGINT,
            do_location_id        BIGINT,
            payment_type          BIGINT,
            fare_amount           DOUBLE,
            extra                 DOUBLE,
            mta_tax               DOUBLE,
            tip_amount            DOUBLE,
            tolls_amount          DOUBLE,
            improvement_surcharge DOUBLE,
            total_amount          DOUBLE,
            congestion_surcharge  DOUBLE,
            airport_fee           DOUBLE
        )
        USING iceberg
        PARTITIONED BY (days(tpep_pickup_datetime))
        """
    )


def transform_bronze_to_silver(bronze_df: DataFrame) -> DataFrame:
    """Apply Silver-layer filtering and de-duplication rules."""
    return bronze_df.filter(
        (col("trip_distance") > 0)
        & (col("total_amount") > 0)
        & (col("passenger_count").isNotNull())
    ).dropDuplicates(["vendor_id", "tpep_pickup_datetime", "passenger_count"])


def run_silver_pipeline(project_id: str, warehouse_uri: str, retain_snapshots: int) -> None:
    spark = build_spark_session(warehouse_uri)

    # ------------------------------------------------------------------ #
    # 2. Read Bronze Data
    # ------------------------------------------------------------------ #
    logger.info("Reading Bronze Iceberg table …")
    bronze_df = spark.read.format("iceberg").load("gcs_catalog.bronze.yellow_trips")

    # ------------------------------------------------------------------ #
    # 3. Clean and Filter
    # ------------------------------------------------------------------ #
    logger.info("Cleaning and filtering …")
    silver_df = transform_bronze_to_silver(bronze_df)

    # ------------------------------------------------------------------ #
    # 4. Ensure the Silver table exists
    # ------------------------------------------------------------------ #
    ensure_silver_table(spark)

    # ------------------------------------------------------------------ #
    # 5. Create Temporary View for MERGE Operation
    # ------------------------------------------------------------------ #
    silver_df.createOrReplaceTempView("silver_updates")

    # ------------------------------------------------------------------ #
    # 6. Merge into Silver Iceberg Table (idempotent execution)
    # ------------------------------------------------------------------ #
    logger.info("Running MERGE INTO gcs_catalog.silver.yellow_trips …")
    spark.sql(
        """
        MERGE INTO gcs_catalog.silver.yellow_trips t
        USING silver_updates s
        ON  t.vendor_id            = s.vendor_id
        AND t.tpep_pickup_datetime = s.tpep_pickup_datetime
        WHEN MATCHED THEN
            UPDATE SET *
        WHEN NOT MATCHED THEN
            INSERT *
        """
    )

    # ------------------------------------------------------------------ #
    # 7. Iceberg Table Maintenance
    # ------------------------------------------------------------------ #
    logger.info("Running compaction (rewrite_data_files) …")
    spark.sql(
        "CALL gcs_catalog.system.rewrite_data_files("
        "  table => 'silver.yellow_trips',"
        "  strategy => 'sort',"
        "  sort_order => 'tpep_pickup_datetime ASC NULLS LAST'"
        ")"
    )

    logger.info("Expiring old snapshots (retain_last=%d) …", retain_snapshots)
    spark.sql(
        f"CALL gcs_catalog.system.expire_snapshots("
        f"  table => 'silver.yellow_trips',"
        f"  retain_last => {retain_snapshots}"
        f")"
    )

    logger.info("Pipeline complete.")
    spark.stop()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
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
    warehouse = args.warehouse or f"gs://{args.project_id}-iceberg-warehouse/warehouse"
    run_silver_pipeline(
        project_id=args.project_id,
        warehouse_uri=warehouse,
        retain_snapshots=args.retain_snapshots,
    )
