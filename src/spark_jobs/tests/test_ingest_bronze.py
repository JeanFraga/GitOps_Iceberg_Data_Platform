"""
Unit tests for ingest_bronze.py column normalisation and argument parsing.
Pure-Python checks: no SparkSession required.
"""

from datetime import datetime

import pytest

from ingest_bronze import parse_args, period_bounds, to_snake_case


class TestSnakeCase:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("VendorID", "vendor_id"),
            ("RatecodeID", "ratecode_id"),
            ("PULocationID", "pu_location_id"),
            ("DOLocationID", "do_location_id"),
            ("Airport_fee", "airport_fee"),
            ("tpep_pickup_datetime", "tpep_pickup_datetime"),
            ("store_and_fwd_flag", "store_and_fwd_flag"),
            ("total amount", "total_amount"),
        ],
    )
    def test_normalises_tlc_columns(self, raw, expected):
        assert to_snake_case(raw) == expected

    def test_is_idempotent(self):
        for name in ["VendorID", "PULocationID", "DOLocationID"]:
            once = to_snake_case(name)
            assert to_snake_case(once) == once


class TestPeriodBounds:
    def test_mid_year_month(self):
        assert period_bounds("2023-01") == (datetime(2023, 1, 1), datetime(2023, 2, 1))

    def test_december_rolls_into_next_year(self):
        assert period_bounds("2023-12") == (datetime(2023, 12, 1), datetime(2024, 1, 1))

    @pytest.mark.parametrize("bad", ["2023-13", "2023-00", "202301", "2023-1", "jan-2023"])
    def test_rejects_malformed_periods(self, bad):
        with pytest.raises(ValueError):
            period_bounds(bad)


class TestArgumentValidation:
    def test_accepts_gcs_source(self):
        args = parse_args(["--project-id", "demo", "--source-uri", "gs://bucket/x.parquet"])
        assert args.source_uri == "gs://bucket/x.parquet"

    @pytest.mark.parametrize("uri", ["https://example.com/x.parquet", "http://example.com/x.parquet"])
    def test_rejects_http_source(self, uri):
        with pytest.raises(SystemExit):
            parse_args(["--project-id", "demo", "--source-uri", uri])

    def test_accepts_valid_period(self):
        args = parse_args(
            ["--project-id", "demo", "--source-uri", "gs://b/x.parquet", "--period", "2023-01"]
        )
        assert args.period == "2023-01"

    def test_rejects_malformed_period(self):
        with pytest.raises(SystemExit):
            parse_args(
                ["--project-id", "demo", "--source-uri", "gs://b/x.parquet", "--period", "2023-13"]
            )
