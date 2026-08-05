"""
Bronze ingestion job: reads NYC TLC Yellow Taxi Parquet files staged on GCS and
writes them as an Apache Iceberg table into the Bronze layer on GCS.

Usage:
    spark-submit \\
      --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.13:1.5.2 \\
      ingest_bronze.py \\
      --project-id <GCP_PROJECT_ID> \\
      --source-uri gs://<bucket>/landing/yellow_tripdata_2023-01.parquet
"""

import argparse
import logging
import re
import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import days

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


def to_snake_case(name: str) -> str:
    """Normalise a TLC column name (e.g. PULocationID) to snake_case (pu_location_id)."""
    name = name.strip().replace(" ", "_")
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"__+", "_", name).lower()


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


def ingest(warehouse_uri: str, source_uri: str) -> None:
    spark = build_spark_session(warehouse_uri)

    logger.info("Reading source parquet: %s", source_uri)

    raw_df = spark.read.parquet(source_uri)

    # Normalise column names to snake_case
    renamed = raw_df.toDF(*[to_snake_case(c) for c in raw_df.columns])

    # Ensure Bronze namespace exists
    spark.sql("CREATE NAMESPACE IF NOT EXISTS gcs_catalog.bronze")

    # Write / append into the Bronze Iceberg table
    (
        renamed.writeTo("gcs_catalog.bronze.yellow_trips")
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.parquet.compression-codec", "zstd")
        .partitionedBy(days("tpep_pickup_datetime"))
        .createOrReplace()
    )

    logger.info("Bronze ingestion complete from %s.", source_uri)
    spark.stop()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Ingest NYC Taxi data into Bronze Iceberg layer")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--warehouse", default=None)
    parser.add_argument("--source-uri", required=True)
    args = parser.parse_args(argv)

    # Spark's Hadoop FS layer has no http(s) driver, so sources must be staged on GCS first.
    if args.source_uri.startswith(("http://", "https://")):
        parser.error("--source-uri must be a Spark-readable path such as gs://…, not an HTTP URL")

    return args


if __name__ == "__main__":
    args = parse_args()
    warehouse = args.warehouse or f"gs://{args.project_id}-iceberg-warehouse/warehouse"
    ingest(warehouse, args.source_uri)
