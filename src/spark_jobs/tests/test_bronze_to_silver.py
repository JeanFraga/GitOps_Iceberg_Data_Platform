"""
Unit tests for bronze_to_silver.py transformation logic.
Runs with pytest + PySpark in local mode (no GCS required).
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from datetime import datetime


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


@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("test_bronze_to_silver")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def make_df(spark, rows):
    return spark.createDataFrame(rows, schema=SCHEMA)


class TestFiltering:
    def test_removes_zero_distance(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 0.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0, 5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        from pyspark.sql.functions import col
        result = df.filter(
            (col("trip_distance") > 0) &
            (col("total_amount") > 0) &
            col("passenger_count").isNotNull()
        )
        assert result.count() == 1

    def test_removes_zero_amount(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 0.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0, 5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        from pyspark.sql.functions import col
        result = df.filter(
            (col("trip_distance") > 0) &
            (col("total_amount") > 0) &
            col("passenger_count").isNotNull()
        )
        assert result.count() == 1

    def test_removes_null_passenger_count(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), None, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 1.0,  5.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        from pyspark.sql.functions import col
        result = df.filter(
            (col("trip_distance") > 0) &
            (col("total_amount") > 0) &
            col("passenger_count").isNotNull()
        )
        assert result.count() == 1

    def test_keeps_valid_rows(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 2.0, 3.5, 100, 200, 1, 18.5),
            (2, datetime(2023, 1, 2, 12, 0), datetime(2023, 1, 2, 12, 45), 1.0, 7.2, 150, 250, 2, 30.0),
        ]
        df = make_df(spark, rows)
        from pyspark.sql.functions import col
        result = df.filter(
            (col("trip_distance") > 0) &
            (col("total_amount") > 0) &
            col("passenger_count").isNotNull()
        )
        assert result.count() == 2


class TestDeduplication:
    def test_deduplicates_on_key(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
        ]
        df = make_df(spark, rows)
        result = df.dropDuplicates(["vendor_id", "tpep_pickup_datetime", "passenger_count"])
        assert result.count() == 1

    def test_retains_distinct_rows(self, spark):
        rows = [
            (1, datetime(2023, 1, 1, 10, 0), datetime(2023, 1, 1, 10, 30), 1.0, 5.0, 100, 200, 1, 15.0),
            (1, datetime(2023, 1, 1, 11, 0), datetime(2023, 1, 1, 11, 30), 2.0, 6.0, 100, 200, 1, 20.0),
        ]
        df = make_df(spark, rows)
        result = df.dropDuplicates(["vendor_id", "tpep_pickup_datetime", "passenger_count"])
        assert result.count() == 2
