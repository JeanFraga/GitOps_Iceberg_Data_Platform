"""
Bronze ingestion job: downloads NYC TLC Yellow Taxi Parquet files and
writes them as an Apache Iceberg table into the Bronze layer on GCS.

Usage:
    spark-submit \\
      --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \\
      ingest_bronze.py \\
      --project-id <GCP_PROJECT_ID> \\
      --year 2023 --month 1
"""

import argparse
import logging
import sys

from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Public TLC data URL pattern
TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def build_spark_session(warehouse_uri: str) -> SparkSession:
    return (
        SparkSession.builder.appName("Ingest_Bronze_Taxi")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.gcs_catalog", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.gcs_catalog.type", "hadoop")
        .config("spark.sql.catalog.gcs_catalog.warehouse", warehouse_uri)
        .getOrCreate()
    )


def ingest(project_id: str, warehouse_uri: str, year: int, month: int) -> None:
    spark = build_spark_session(warehouse_uri)

    url = f"{TLC_BASE_URL}/yellow_tripdata_{year}-{month:02d}.parquet"
    logger.info("Reading source parquet: %s", url)

    raw_df = spark.read.parquet(url)

    # Normalise column names to snake_case
    renamed = raw_df.toDF(*[c.lower().replace(" ", "_") for c in raw_df.columns])

    # Ensure Bronze namespace exists
    spark.sql("CREATE NAMESPACE IF NOT EXISTS gcs_catalog.bronze")

    # Write / append into the Bronze Iceberg table
    (
        renamed.writeTo("gcs_catalog.bronze.yellow_trips")
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.parquet.compression-codec", "zstd")
        .partitionedBy("days(tpep_pickup_datetime)")
        .createOrReplace()
    )

    logger.info("Bronze ingestion complete for %d-%02d.", year, month)
    spark.stop()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Ingest NYC Taxi data into Bronze Iceberg layer")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--warehouse", default=None)
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--month", type=int, default=1)
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    warehouse = args.warehouse or f"gs://{args.project_id}-iceberg-warehouse/warehouse"
    ingest(args.project_id, warehouse, args.year, args.month)
