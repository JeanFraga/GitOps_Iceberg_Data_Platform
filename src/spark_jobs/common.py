"""Shared configuration for the Spark jobs.

Single source of truth for the Iceberg catalog name, table identifiers, and
the warehouse-bucket naming convention. The bucket name must match the bucket
created by infra/modules/bq_iceberg (``<project_id>-iceberg-warehouse``).

The release workflow (.github/workflows/release.yml) ships this module next to
each entry point via ``--py-files``; for local spark-submit runs pass
``--py-files src/spark_jobs/common.py``.
"""

from pyspark.sql import SparkSession

CATALOG = "gcs_catalog"
BRONZE_TABLE = f"{CATALOG}.bronze.yellow_trips"
SILVER_TABLE = f"{CATALOG}.silver.yellow_trips"

# Canonical trip schema shared by Bronze normalisation and the Silver DDL.
# TLC file vintages add/remove/retype columns; every write is projected onto
# this schema so the tables never drift with the source files.
TRIP_COLUMNS = (
    ("vendor_id", "BIGINT"),
    ("tpep_pickup_datetime", "TIMESTAMP"),
    ("tpep_dropoff_datetime", "TIMESTAMP"),
    ("passenger_count", "DOUBLE"),
    ("trip_distance", "DOUBLE"),
    ("ratecode_id", "DOUBLE"),
    ("store_and_fwd_flag", "STRING"),
    ("pu_location_id", "BIGINT"),
    ("do_location_id", "BIGINT"),
    ("payment_type", "BIGINT"),
    ("fare_amount", "DOUBLE"),
    ("extra", "DOUBLE"),
    ("mta_tax", "DOUBLE"),
    ("tip_amount", "DOUBLE"),
    ("tolls_amount", "DOUBLE"),
    ("improvement_surcharge", "DOUBLE"),
    ("total_amount", "DOUBLE"),
    ("congestion_surcharge", "DOUBLE"),
    ("airport_fee", "DOUBLE"),
)


def default_warehouse_uri(project_id: str) -> str:
    """Default Iceberg warehouse URI, derived from the Terraform bucket name."""
    return f"gs://{project_id}-iceberg-warehouse/warehouse"


def build_spark_session(app_name: str, warehouse_uri: str) -> SparkSession:
    """Build a SparkSession with the Iceberg catalog pointed at the warehouse."""
    return (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(f"spark.sql.catalog.{CATALOG}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{CATALOG}.type", "hadoop")
        .config(f"spark.sql.catalog.{CATALOG}.warehouse", warehouse_uri)
        .config("spark.sql.iceberg.vectorization.enabled", "true")
        .getOrCreate()
    )
