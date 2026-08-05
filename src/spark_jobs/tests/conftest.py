"""Shared pytest fixtures for the Spark job tests."""

import sys
from pathlib import Path

# Make src/spark_jobs importable regardless of the pytest working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pyspark.sql import SparkSession

from common import CATALOG

# Scala 2.12 build: pip-installed PySpark ships Scala 2.12, unlike the Dataproc
# runtime (Scala 2.13) targeted by ICEBERG_SPARK_PACKAGE in release.yml.
ICEBERG_LOCAL_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2"


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """Local SparkSession with a real Iceberg catalog backed by a temp dir.

    Used by both the pure-transform unit tests and the Iceberg integration
    tests, so table DDL, writes, and MERGE behaviour can be exercised without
    GCS. Downloads the Iceberg runtime jar from Maven Central on first run.
    """
    warehouse = tmp_path_factory.mktemp("iceberg_warehouse")
    session = (
        SparkSession.builder.master("local[1]")
        .appName("spark_jobs_tests")
        .config("spark.jars.packages", ICEBERG_LOCAL_PACKAGE)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(f"spark.sql.catalog.{CATALOG}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{CATALOG}.type", "hadoop")
        .config(f"spark.sql.catalog.{CATALOG}.warehouse", str(warehouse))
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
