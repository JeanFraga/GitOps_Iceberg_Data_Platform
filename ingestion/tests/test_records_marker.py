import base64
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config.fingerprint import fingerprint
from ingestion import bronze
from ingestion.marker import UnmarkedFile, check_marker, drop_marker_line
from ingestion.records import split

SAMPLE = Path(__file__).resolve().parents[2] / "datagen/samples/payer_b/members/payer_b_members_2024.csv"
MARKER = b"# SYNTHETIC-DATA-NO-REAL-PHI\n"


def rows_for(data: bytes):
    check_marker(data)
    return bronze.build_rows(
        drop_marker_line(split(data, "csv")), ingested_at=datetime(2026, 10, 8, tzinfo=UTC),
        source_file="gs://b/x.csv", record_source="payer_b.members", sha256="0" * 64, run_id="r1",
    )  # fmt: skip


def test_happy_path_sample():
    data = SAMPLE.read_bytes()
    lines = data.decode().splitlines()
    cols, rows = rows_for(data)
    assert len(rows) == len(lines) - 2 == 720
    raw_i, ord_i = len(cols), len(cols) + 2
    assert [r[ord_i] for r in rows] == list(range(3, 723))
    assert [r[raw_i] for r in rows] == lines[2:]
    assert all(isinstance(v, str) or v is None for r in rows for v in r[: len(cols)])


def test_unmarked_is_refused():
    with pytest.raises(UnmarkedFile):
        check_marker(b"member_id,dob\nM1,2000-01-01\n")


def test_marker_beyond_within_bytes_is_refused():
    with pytest.raises(UnmarkedFile):
        check_marker(b"a\n" * 3000 + MARKER)


def test_marker_drop_header_is_line_two_and_fingerprint_excludes_marker():
    data = MARKER + b"member_id,dob\nM1,2000-01-01\n"
    recs = drop_marker_line(split(data, "csv"))
    assert recs[0].ordinal == 2 and recs[0].raw == b"member_id,dob"
    assert fingerprint(recs[0].raw.decode(), "csv") == fingerprint("member_id,dob\n", "csv")
    cols, rows = rows_for(data)
    assert cols == ["member_id", "dob"] and rows[0][:2] == ("M1", "2000-01-01") and rows[0][4] == 3


def test_bom_stripped_before_marker_and_split():
    data = b"\xef\xbb\xbf" + MARKER + b"id\n1\n"
    cols, rows = rows_for(data)
    assert cols == ["id"] and rows[0][0] == "1" and rows[0][1] == "1" and rows[0][3] == 3


def test_crlf_terminator_excluded():
    data = MARKER.replace(b"\n", b"\r\n") + b"id,n\r\n1,a\r\n2,b\r\n"
    _, rows = rows_for(data)
    assert [r[2] for r in rows] == ["1,a", "2,b"]
    assert [r[4] for r in rows] == [3, 4]


def test_quoted_newline_keeps_record_and_start_ordinal():
    data = MARKER + b'id,addr\n1,"a\nb"\n2,c\n'
    _, rows = rows_for(data)
    assert [r[:2] for r in rows] == [("1", "a\nb"), ("2", "c")]
    assert [r[4] for r in rows] == [3, 5]


def test_non_utf8_record_stored_base64():
    data = MARKER + b"id\n\xff\xfe\n"
    _, rows = rows_for(data)
    assert rows[0][0] is None and rows[0][2] == "base64"
    assert base64.b64decode(rows[0][1]) == b"\xff\xfe"
