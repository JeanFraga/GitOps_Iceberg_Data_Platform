"""
Bronze ingestion job: reads NYC TLC Yellow Taxi Parquet files staged on GCS and
writes them as an Apache Iceberg table into the Bronze layer on GCS.

Runs on Dataproc Serverless via .github/workflows/release.yml, which supplies
the Iceberg runtime coordinate (ICEBERG_SPARK_PACKAGE) and ships common.py via
--py-files. Local runs additionally need a GCS connector jar for gs:// access
(pip PySpark ships none) — see the README Quick-Start for the exact command.

Pass --period YYYY-MM (the file's nominal month) so stray out-of-month rows
cannot overwrite other months' partitions.
"""

import argparse
import logging
import re
import sys
from datetime import datetime

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, days, lit

from common import (
    BRONZE_TABLE,
    CATALOG,
    TRIP_COLUMNS,
    build_spark_session,
    default_warehouse_uri,
)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


def to_snake_case(name: str) -> str:
    """Normalise a TLC column name (e.g. PULocationID) to snake_case (pu_location_id)."""
    name = name.strip().replace(" ", "_")
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"__+", "_", name).lower()


def normalize_to_trip_schema(df: DataFrame) -> DataFrame:
    """Project onto the canonical trip schema.

    TLC parquet schemas vary by vintage (added columns, INT64/DOUBLE flips);
    the Bronze table is created once, so every write must match its schema:
    matching columns are cast, missing ones filled with NULL, unknown dropped.
    """
    known = {name for name, _ in TRIP_COLUMNS}
    dropped = sorted(set(df.columns) - known)
    if dropped:
        logger.warning("Dropping columns not in the canonical trip schema: %s", dropped)
    missing = [name for name, _ in TRIP_COLUMNS if name not in df.columns]
    if missing:
        logger.warning("Source lacks canonical columns (filled with NULL): %s", missing)
    return df.select(
        [
            (col(name) if name in df.columns else lit(None)).cast(dtype).alias(name)
            for name, dtype in TRIP_COLUMNS
        ]
    )


def period_bounds(period: str):
    """Return [start, end) datetimes for a 'YYYY-MM' period string."""
    match = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if not match:
        raise ValueError(f"period must look like YYYY-MM, got {period!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"period month out of range: {period!r}")
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def filter_to_period(df: DataFrame, period: str) -> DataFrame:
    """Keep only rows whose pickup falls inside the period.

    TLC monthly files contain stray out-of-month rows (midnight spillover and
    corrupt dates). Without this filter a single stray row makes
    overwritePartitions() replace a whole day partition of another month.
    """
    start, end = period_bounds(period)
    return df.filter(
        (col("tpep_pickup_datetime") >= lit(start)) & (col("tpep_pickup_datetime") < lit(end))
    )


def write_bronze(df: DataFrame) -> None:
    """Write one source file's rows into the Bronze table.

    Replaces only the day partitions present in ``df``, so re-running a month
    is idempotent and never clobbers other months (callers must period-filter
    the dataframe first — see filter_to_period).
    """
    spark = df.sparkSession
    if spark.catalog.tableExists(BRONZE_TABLE):
        df.writeTo(BRONZE_TABLE).overwritePartitions()
    else:
        (
            df.writeTo(BRONZE_TABLE)
            .tableProperty("write.format.default", "parquet")
            .tableProperty("write.parquet.compression-codec", "zstd")
            .partitionedBy(days("tpep_pickup_datetime"))
            .create()
        )


def ingest(warehouse_uri: str, source_uri: str, period: str = None) -> None:
    spark = build_spark_session("Ingest_Bronze_Taxi", warehouse_uri)

    logger.info("Reading source parquet: %s", source_uri)
    raw_df = spark.read.parquet(source_uri)

    renamed = raw_df.toDF(*[to_snake_case(c) for c in raw_df.columns])
    normalized = normalize_to_trip_schema(renamed)

    if period:
        start, end = period_bounds(period)
        in_period = (col("tpep_pickup_datetime") >= lit(start)) & (col("tpep_pickup_datetime") < lit(end))
        dropped = normalized.filter(~in_period).count()
        normalized = normalized.filter(in_period)
        if dropped:
            logger.warning("Dropped %d rows with pickups outside period %s", dropped, period)
    else:
        logger.warning(
            "No --period given; stray out-of-month rows in the source can "
            "overwrite other months' day partitions"
        )

    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.bronze")
    write_bronze(normalized)

    logger.info("Bronze ingestion complete from %s.", source_uri)
    spark.stop()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Ingest NYC Taxi data into Bronze Iceberg layer")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--warehouse", default=None)
    parser.add_argument("--source-uri", required=True)
    parser.add_argument(
        "--period",
        default=None,
        help="Nominal month of the source file as YYYY-MM; rows outside it are dropped",
    )
    args = parser.parse_args(argv)

    # Spark's Hadoop FS layer has no http(s) driver, so sources must be staged on GCS first.
    if args.source_uri.startswith(("http://", "https://")):
        parser.error("--source-uri must be a Spark-readable path such as gs://…, not an HTTP URL")

    if args.period is not None:
        try:
            period_bounds(args.period)
        except ValueError as exc:
            parser.error(str(exc))

    return args


if __name__ == "__main__":
    args = parse_args()
    warehouse = args.warehouse or default_warehouse_uri(args.project_id)
    ingest(warehouse, args.source_uri, period=args.period)
