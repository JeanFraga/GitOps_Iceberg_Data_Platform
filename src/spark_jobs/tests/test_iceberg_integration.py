"""
Integration tests running the jobs' Iceberg logic against a real local
catalog (see the ``spark`` fixture in conftest.py). Covers the behaviour unit
tests cannot: table DDL, Bronze write semantics, and MERGE INTO.
"""

from datetime import datetime

import pytest
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from bronze_to_silver import (
    ensure_silver_table,
    merge_into_silver,
    transform_bronze_to_silver,
)
from common import BRONZE_TABLE, CATALOG, SILVER_TABLE, TRIP_COLUMNS
from ingest_bronze import filter_to_period, normalize_to_trip_schema, write_bronze

# Mirrors the Silver DDL in bronze_to_silver.ensure_silver_table.
FULL_SCHEMA = StructType(
    [
        StructField("vendor_id", LongType()),
        StructField("tpep_pickup_datetime", TimestampType()),
        StructField("tpep_dropoff_datetime", TimestampType()),
        StructField("passenger_count", DoubleType()),
        StructField("trip_distance", DoubleType()),
        StructField("ratecode_id", DoubleType()),
        StructField("store_and_fwd_flag", StringType()),
        StructField("pu_location_id", LongType()),
        StructField("do_location_id", LongType()),
        StructField("payment_type", LongType()),
        StructField("fare_amount", DoubleType()),
        StructField("extra", DoubleType()),
        StructField("mta_tax", DoubleType()),
        StructField("tip_amount", DoubleType()),
        StructField("tolls_amount", DoubleType()),
        StructField("improvement_surcharge", DoubleType()),
        StructField("total_amount", DoubleType()),
        StructField("congestion_surcharge", DoubleType()),
        StructField("airport_fee", DoubleType()),
    ]
)


def trip(vendor_id, pickup, passenger_count=1.0, trip_distance=5.0, total_amount=20.0,
         pu_location_id=100, do_location_id=200):
    return (
        vendor_id, pickup, pickup, passenger_count, trip_distance, 1.0, "N",
        pu_location_id, do_location_id, 1, 10.0, 0.5, 0.5, 2.0, 0.0, 0.3,
        total_amount, 2.5, 0.0,
    )


def trips_df(spark, rows):
    return spark.createDataFrame(rows, schema=FULL_SCHEMA)


@pytest.fixture(autouse=True)
def clean_tables(spark):
    for table in (BRONZE_TABLE, SILVER_TABLE):
        spark.sql(f"DROP TABLE IF EXISTS {table}")
    yield
    for table in (BRONZE_TABLE, SILVER_TABLE):
        spark.sql(f"DROP TABLE IF EXISTS {table}")


class TestBronzeWriteSemantics:
    def test_monthly_loads_accumulate_and_rerun_is_idempotent(self, spark):
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.bronze")

        january = trips_df(
            spark,
            [trip(1, datetime(2023, 1, 1, 10, 0)), trip(1, datetime(2023, 1, 2, 10, 0))],
        )
        write_bronze(january)
        assert spark.table(BRONZE_TABLE).count() == 2

        # A different month must append, not wipe January.
        february = trips_df(spark, [trip(1, datetime(2023, 2, 1, 10, 0))])
        write_bronze(february)
        assert spark.table(BRONZE_TABLE).count() == 3

        # Re-running a day replaces only that day's partition.
        january_redo = trips_df(spark, [trip(2, datetime(2023, 1, 1, 10, 0))])
        write_bronze(january_redo)
        result = spark.table(BRONZE_TABLE)
        assert result.count() == 3
        day_one = result.filter("DATE(tpep_pickup_datetime) = '2023-01-01'").collect()
        assert [r.vendor_id for r in day_one] == [2]

    def test_period_filter_stops_stray_rows_wiping_other_months(self, spark):
        """Real TLC monthly files contain out-of-month rows; unfiltered, one
        stray row would replace a whole day partition of another month."""
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.bronze")

        january = trips_df(
            spark,
            [trip(1, datetime(2023, 1, 31, 10, 0)), trip(1, datetime(2023, 1, 31, 11, 0))],
        )
        write_bronze(filter_to_period(january, "2023-01"))
        assert spark.table(BRONZE_TABLE).count() == 2

        # The "February file" carries a stray row dated 31 January.
        february = trips_df(
            spark,
            [trip(2, datetime(2023, 2, 1, 9, 0)), trip(2, datetime(2023, 1, 31, 23, 59))],
        )
        write_bronze(filter_to_period(february, "2023-02"))

        result = spark.table(BRONZE_TABLE)
        assert result.count() == 3  # stray row dropped, January intact
        jan_31 = result.filter("DATE(tpep_pickup_datetime) = '2023-01-31'")
        assert jan_31.count() == 2
        assert [r.vendor_id for r in jan_31.collect()] == [1, 1]


class TestSchemaNormalisation:
    def test_missing_extra_and_retyped_columns_are_normalised(self, spark):
        """A different TLC vintage (added column, missing column, int-typed
        passenger_count) must still project onto the canonical schema."""
        vintage = spark.createDataFrame(
            [(1, datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 10, 30), 2, 0.75)],
            schema="vendor_id long, tpep_pickup_datetime timestamp, "
                   "tpep_dropoff_datetime timestamp, passenger_count long, "
                   "cbd_congestion_fee double",
        )
        result = normalize_to_trip_schema(vintage)

        assert [f.name for f in result.schema.fields] == [name for name, _ in TRIP_COLUMNS]
        assert "cbd_congestion_fee" not in result.columns
        row = result.collect()[0]
        assert row.passenger_count == 2.0  # cast long -> double
        assert row.total_amount is None    # missing column filled with NULL


class TestSilverMerge:
    def test_merge_is_idempotent_and_updates(self, spark):
        ensure_silver_table(spark)
        pickup_a = datetime(2023, 1, 1, 10, 0)
        pickup_b = datetime(2023, 1, 1, 11, 0)
        df = trips_df(spark, [trip(1, pickup_a), trip(2, pickup_b)])

        merge_into_silver(spark, df)
        assert spark.table(SILVER_TABLE).count() == 2

        merge_into_silver(spark, df)
        assert spark.table(SILVER_TABLE).count() == 2

        updated = trips_df(spark, [trip(1, pickup_a, total_amount=99.0)])
        merge_into_silver(spark, updated)
        result = spark.table(SILVER_TABLE)
        assert result.count() == 2
        row = result.filter("vendor_id = 1").collect()[0]
        assert row.total_amount == 99.0

    def test_transform_output_merges_without_cardinality_error(self, spark):
        """Bronze rows sharing MERGE_KEYS but differing elsewhere must merge
        cleanly — this is the dedup-key/merge-key drift regression test."""
        ensure_silver_table(spark)
        pickup = datetime(2023, 1, 1, 10, 0)
        bronze = trips_df(
            spark,
            [trip(1, pickup, passenger_count=1.0), trip(1, pickup, passenger_count=3.0)],
        )
        silver = transform_bronze_to_silver(bronze)

        merge_into_silver(spark, silver)
        merge_into_silver(spark, silver)
        assert spark.table(SILVER_TABLE).count() == 1
