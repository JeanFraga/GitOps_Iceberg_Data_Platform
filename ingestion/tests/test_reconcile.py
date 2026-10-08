import base64

from ingestion.reconcile import gate, row_bytes
from ingestion.records import Record

RECS = [Record(3, b"M1,a"), Record(4, b"M2,b"), Record(5, b"\xff\xfe")]
ROWS = [(3, "M1,a", "utf-8"), (4, "M2,b", "utf-8"), (5, base64.b64encode(b"\xff\xfe").decode(), "base64")]


def test_pass_including_base64_rows():
    r = gate(RECS, reversed(ROWS))
    assert r.passed and r.expected == r.actual == 3


def test_count_mismatch():
    r = gate(RECS, ROWS[:2])
    assert not r.passed and r.detail == {"check": "count", "expected": 3, "actual": 2}


def test_hash_mismatch_reports_first_ordinal_and_no_values():
    r = gate(RECS, [ROWS[0], (4, "M2,X", "utf-8"), ROWS[2]])
    assert not r.passed and r.mismatches == 1 and r.first_mismatch_ordinal == 4
    assert "M2" not in str(r.detail)


def test_duplicate_ordinal_with_equal_count_fails():
    r = gate(RECS, [ROWS[0], ROWS[0], ROWS[2]])
    assert not r.passed and r.first_mismatch_ordinal == 4


def test_row_bytes_none():
    assert row_bytes(None, "utf-8") == b""
