"""
Unit tests for ingest_bronze.py column normalisation and argument parsing.
Pure-Python checks: no SparkSession required.
"""

import pytest
from pathlib import Path
import sys

# Ensure src/spark_jobs is importable regardless of pytest working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest_bronze import parse_args, to_snake_case


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


class TestArgumentValidation:
    def test_accepts_gcs_source(self):
        args = parse_args(["--project-id", "demo", "--source-uri", "gs://bucket/x.parquet"])
        assert args.source_uri == "gs://bucket/x.parquet"

    @pytest.mark.parametrize("uri", ["https://example.com/x.parquet", "http://example.com/x.parquet"])
    def test_rejects_http_source(self, uri):
        with pytest.raises(SystemExit):
            parse_args(["--project-id", "demo", "--source-uri", uri])
