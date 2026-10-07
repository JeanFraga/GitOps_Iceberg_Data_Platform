"""Python engine runs the AD-7 hash and AD-22 fingerprint golden vectors."""

import datetime as dt
import hashlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fingerprint
import hashing

STANDARDS = Path(__file__).resolve().parent / "standards"
HASH_VECTORS = yaml.safe_load((STANDARDS / "hashing.yaml").read_text())["golden_vectors"]
FP_SPEC = yaml.safe_load((STANDARDS / "fingerprint.yaml").read_text())
FP_VECTORS = FP_SPEC["golden_vectors"]

TYPES = {
    None: lambda v: v,
    "date": dt.date.fromisoformat,
    "timestamp": dt.datetime.fromisoformat,
    "decimal": Decimal,
    "boolean": lambda v: v,
    "float": float,
}
ERRORS = {
    "all_null_business_key": hashing.AllNullBusinessKeyError,
    "naive_timestamp": ValueError,
    "float": TypeError,
    "non_finite_decimal": ValueError,
}


def _values(vector):
    return [TYPES[item.get("type")](item["v"]) for item in vector["values"]]


@pytest.mark.parametrize("vector", HASH_VECTORS, ids=[v["name"] for v in HASH_VECTORS])
def test_hash_golden_vector(vector):
    business_key = vector["kind"] == "business_key"
    fn = hashing.hash_key if business_key else hashing.hashdiff
    if "error" in vector:
        with pytest.raises(ERRORS[vector["error"]]):
            fn(_values(vector))
        return
    assert hashing.hash_input(_values(vector), business_key) == vector["canonical"]
    assert hashlib.md5(vector["canonical"].encode()).hexdigest().upper() == vector["md5"]
    assert fn(_values(vector)) == vector["md5"]


@pytest.mark.parametrize("vector", FP_VECTORS, ids=[v["name"] for v in FP_VECTORS])
def test_fingerprint_golden_vector(vector):
    assert fingerprint.LAYOUTS[vector["format"]](vector["input"]) == vector["layout"]
    fp = fingerprint.fingerprint(vector["input"], vector["format"])
    assert fp == vector["sha256"]
    assert fingerprint.fp8(fp) == vector["fp8"]


def test_jsonl_sample_size_matches_spec():
    assert FP_SPEC["spec"]["formats"]["jsonl"]["N"] == fingerprint.JSONL_SAMPLE_RECORDS


def test_jsonl_ignores_records_past_sample():
    text = '{"a":1}\n{"b":2}\n'
    assert fingerprint.jsonl_layout(text, sample=1) == ["a"]


def test_jsonl_keeps_unicode_line_separator_inside_strings():
    assert fingerprint.jsonl_layout('{"a":"x\u2028y"}\r\n{"b":1}\n') == ["a", "b"]


def test_csv_without_header_rejected():
    with pytest.raises(ValueError):
        fingerprint.fingerprint("", "csv")
