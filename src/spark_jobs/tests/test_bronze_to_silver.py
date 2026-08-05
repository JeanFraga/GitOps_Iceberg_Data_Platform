"""
Unit tests for bronze_to_silver.py transformation logic.
Runs with pytest + PySpark in local mode (no GCS required).
"""

from datetime import datetime

import pytest
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StructField,
    StructType,
    TimestampType,
)

from bronze_to_silver import MERGE_KEYS, parse_args, transform_bronze_to_silver

SCHEMA = StructType(
    [
        StructField("vendor_id", LongType(), True),
        StructField("tpep_pickup_datetime", TimestampType(), True),
        StructField("tpep_dropoff_datetime", TimestampType(), True),
        StructField("passenger_count", DoubleType(), True),
        StructField("trip_distance", DoubleType(), True),
        StructField("pu_location_id", LongType(), True),
        StructField("do_location_id", LongType(), True),
        StructField("payment_type", LongType(), True),
        StructField("total_amount", DoubleType(), True),
    ]
)


def make_df(spark, rows):
    return spark.createDataFrame(rows, schema=SCHEMA)


class TestFiltering:
    def test_removes_zero_distance(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 0.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0, 5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1

    def test_removes_zero_amount(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 0.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0, 5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1

    def test_removes_null_passenger_count(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), None, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0,  5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1

    def test_keeps_valid_rows(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 2.0, 3.5, 100, 200, 1, 18.5),
            (2, datetime(2023, 1, 2, 12, 0), datetime(2023, 1, 2, 12, 45), 1.0, 7.2, 150, 250, 2, 30.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 2


class TestDeduplication:
    def test_deduplicates_on_key(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1

    def test_retains_distinct_rows(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 2.0, 6.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 2

    def test_output_unique_on_merge_keys(self, spark):
        """Rows differing only outside MERGE_KEYS must collapse to one row,
        otherwise the downstream MERGE INTO hits a cardinality violation."""
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 3.0, 5.0, 100, 200, 1, 15.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1
        assert result.select(*MERGE_KEYS).distinct().count() == result.count()

    def test_retains_distinct_same_second_trips(self, spark):
        """Distinct trips sharing a vendor and pickup second are routine in
        real TLC data; the key must not collapse them (data-loss regression)."""
        pickup = datetime(2023, 1, 1, 10, 0)
        rows = [
            (1, pickup, datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, pickup, datetime(2023, 1, 1, 10, 45), 1.0, 7.0, 101, 250, 1, 22.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 2

    def test_drops_rows_missing_a_merge_key_component(self, spark):
        """A NULL key component never matches in MERGE ON and would duplicate
        on every re-run, so such rows are filtered out."""
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, None, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0, 5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = transform_bronze_to_silver(df)
        assert result.count() == 1


class TestArgumentValidation:
    def test_rejects_non_positive_retain_snapshots(self):
        with pytest.raises(SystemExit):
            parse_args(["--project-id", "demo-project", "--retain-snapshots", "0"])
