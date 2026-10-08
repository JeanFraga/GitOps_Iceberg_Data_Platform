"""Story 5: NDJSON and X12 into Bronze (format choice, split, row layout, reconcile, local-Spark WAP)."""

import base64
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

import ingestion.__main__ as cli
from ingestion import bronze, reconcile
from ingestion.records import split
from ingestion.tests.test_main import FakeOps, fake_gcloud

SAMPLES = Path(__file__).resolve().parents[2] / "datagen" / "samples"
NDJSON = SAMPLES / "emr_facility_1/patient/emr_facility_1_patient_F1.ndjson"
X12 = SAMPLES / "payer_a/835/payer_a_835_p_A1.835"
CFG = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": {}}
ISA = b"ISA*00*          *00*          *ZZ*PAYERA         *ZZ*PAYERACH1      *240714*1200*^*00501*000000001*0*T*:~"
X12_BODY = [b"GS*HP*PAYERA*PAYERACH1*20240714*1200*1*X*005010X221A1", b"ST*835*0001*005010X221A1",
            b"REF*EV*SYNTHETIC-DATA-NO-REAL-PHI", b"SE*3*0001", b"GE*1*1", b"IEA*1*000000001"]  # fmt: skip


def rows(records, fmt):
    return bronze.build_rows(records, fmt, ingested_at=datetime(2026, 10, 8, tzinfo=UTC), source_file="gs://b/x",
                             record_source="s.f", sha256="0" * 64, run_id="r1")  # fmt: skip


def gate_rows(built, ncols):
    return [(r[ncols + 2], r[ncols], r[ncols + 1]) for r in built]


def uri(source, feed, data, name):
    sha = hashlib.sha256(data).hexdigest()
    return sha, f"gs://b/source={source}/feed={feed}/ingest_date=2026-10-08/sha256={sha}/{name}"


@pytest.mark.parametrize(("name", "fmt"), [("a.csv", "csv"), ("a.ndjson", "jsonl"), ("A.JSONL", "jsonl"),
                                           ("a.834", "x12"), ("a.835", "x12"), ("a.837", "x12"),
                                           ("a.txt", None), ("a.x12", None)])  # fmt: skip
def test_format_of(name, fmt):
    assert cli.format_of(f"gs://b/source=s/feed=f/ingest_date=d/sha256=x/{name}") == fmt


def test_ndjson_happy_one_row_per_line_verbatim():
    data = NDJSON.read_bytes()
    recs = split(data, "jsonl")
    cols, built = rows(recs, "jsonl")
    lines = data.split(b"\n")
    assert cols == ["record"] and len(built) == len([x for x in lines if x.strip()])
    assert built[0][0] == lines[0].decode() and built[0][1] == built[0][0] and built[0][3] == 1
    assert [r[3] for r in built] == list(range(1, len(built) + 1))
    assert reconcile.gate(bronze.data_records(recs, "jsonl"), gate_rows(built, 1)).passed


def test_ndjson_blank_lines_skipped_with_physical_ordinals():
    data = b'{"a":1}\n\n{"a":2}\r\n\r\n   \n{"a":3}\n'
    recs = split(data, "jsonl")
    assert [(r.ordinal, r.raw) for r in recs] == [(1, b'{"a":1}'), (3, b'{"a":2}'), (6, b'{"a":3}')]
    _cols, built = rows(recs, "jsonl")
    assert len(built) == len(recs) == 3
    assert reconcile.gate(recs, gate_rows(built, 1)).passed


def test_x12_single_line_and_line_broken_give_same_rows():
    one = ISA + b"~".join(X12_BODY) + b"~"
    broken = ISA + b"\n" + b"~\r\n".join(X12_BODY) + b"~\n"
    a, b = split(one, "x12"), split(broken, "x12")
    assert [(r.ordinal, r.raw) for r in a] == [(r.ordinal, r.raw) for r in b]
    cols, built = rows(a, "x12")
    assert cols == ["segment_id", "segment"]
    assert [r[0] for r in built] == ["ISA", "GS", "ST", "REF", "SE", "GE", "IEA"]
    assert built[0][1] == ISA[:-1].decode() and built[0][2] == built[0][1]
    assert [r[4] for r in built] == list(range(1, 8)) and not any(b"~" in r.raw for r in a)
    assert reconcile.gate(a, gate_rows(built, 2)).passed


def test_x12_committed_sample_reconciles():
    recs = split(X12.read_bytes(), "x12")
    _cols, built = rows(recs, "x12")
    assert len(built) == len(recs) and all("\n" not in r[1] and not r[1].endswith("~") for r in built)
    assert reconcile.gate(recs, gate_rows(built, 2)).passed


@pytest.mark.parametrize("fmt", ["jsonl", "x12"])
def test_non_utf8_record_is_base64_with_null_data(fmt):
    if fmt == "jsonl":
        data, ncols, bad_ordinal = b'{"a":1}\n{"a":"\xff"}\n', 1, 2
    else:
        data, ncols, bad_ordinal = ISA + b"GS*\xff~ST*835*1~", 2, 2
    recs = split(data, fmt)
    _cols, built = rows(recs, fmt)
    bad = next(r for r in built if r[ncols + 2] == bad_ordinal)
    raw = next(r.raw for r in recs if r.ordinal == bad_ordinal)
    assert bad[:ncols] == (None,) * ncols and bad[ncols + 1] == "base64"
    assert base64.b64decode(bad[ncols]) == raw
    assert reconcile.gate(recs, gate_rows(built, ncols)).passed


def test_bad_x12_head_raises_before_any_write(monkeypatch):
    data = b"ISA*00*SYNTHETIC-DATA-NO-REAL-PHI~GS*1~"
    _sha, u = uri("payer_a", "835", data, "x.835")
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    ops = FakeOps().install(monkeypatch)
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: pytest.fail("Spark started"))
    with pytest.raises(ValueError):
        cli.load(CFG, u, "r1")
    assert ops.lifecycle == []


def test_bad_x12_head_main_exits_nonzero_type_only(monkeypatch, capsys):
    data = b"ISA*00*SYNTHETIC-DATA-NO-REAL-PHI~GS*1~"
    _sha, u = uri("payer_a", "835", data, "x.835")
    cfg = {**CFG, "profile": "demo", "run": {"lock_ttl_minutes": 1}}
    monkeypatch.setattr(cli.yaml, "safe_load", lambda _: cfg)
    monkeypatch.setattr(cli.runner, "BigQueryBackend", lambda *a: cli.runner.FakeBackend())
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    FakeOps().install(monkeypatch)
    assert cli.main(["--profile", "demo", "--file", u]) == 1
    last = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert last == {"event": "error", "error_type": "ValueError", "error": "load failed"}


# --- local Spark WAP (no GCP) ---------------------------------------------------------------------

java = pytest.mark.skipif(shutil.which("java") is None, reason="Java not installed")
VERSIONS = yaml.safe_load((SAMPLES.parents[1] / "versions.yaml").read_text())
CASES = {
    "jsonl": ("emr_facility_1", "patient", NDJSON, "patient__f1"),
    "x12": ("payer_a", "835", X12, "835__a1"),
    "jsonl_blank": ("emr_facility_1", "patient", None, "patient__f1"),
    "jsonl_badbyte": ("emr_facility_1", "patient", None, "patient__f1"),
    "x12_834": ("payer_a", "834", SAMPLES / "payer_a/834/payer_a_834_full_20240101.834", None),
}


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    if shutil.which("java") is None:
        pytest.skip("Java not installed")
    s = bronze.build_session(bronze.hadoop_catalog_conf(str(tmp_path_factory.mktemp("wh"))), VERSIONS)
    s.stop = lambda: None
    yield s
    type(s).stop(s)


def ident_of(ref):
    _p, _w, ns, table = ref.split(".", 3)
    return bronze.quoted_ident(ns, table)


@pytest.fixture
def env(monkeypatch, spark, request):
    source, feed, path, _table = CASES[request.param]
    for t in spark.sql(f"SHOW TABLES IN {bronze.CATALOG}.`bronze_{source}`").collect() if spark.catalog.databaseExists(
            f"{bronze.CATALOG}.bronze_{source}") else []:  # fmt: skip
        spark.sql(f"DROP TABLE IF EXISTS {bronze.quoted_ident(f'bronze_{source}', t['tableName'])} PURGE")
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: spark)
    monkeypatch.setattr(cli, "bq_count", lambda p, c, ref, run: {
        "rows": spark.table(ident_of(ref)).where(f"_run_id = '{run}'").count(), "min_ordinal": 1})  # fmt: skip
    lines = NDJSON.read_bytes().split(b"\n")
    if request.param == "jsonl_blank":
        data, name = b"\n".join([lines[0], b"", b"\r", "\u2003".encode(), *lines[1:4]]) + b"\n", "b.ndjson"
    elif request.param == "jsonl_badbyte":
        data, name = b"\n".join([lines[0], b'{"id":1}\xff', *lines[1:4]]) + b"\n", "c.ndjson"
    else:
        data, name = path.read_bytes(), path.name
    _sha, u = uri(source, feed, data, name)
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    return spark, data, u, request.param


@java
@pytest.mark.parametrize("env", ["jsonl", "x12", "x12_834", "jsonl_blank", "jsonl_badbyte"], indirect=True)
def test_wap_reconciles_and_counts_equal_split(monkeypatch, env):
    spark, data, u, case = env
    fmt = "jsonl" if case.startswith("jsonl") else "x12"
    ops = FakeOps().install(monkeypatch)
    out = cli.load({**CFG, "versions": VERSIONS}, u, "r1")
    assert ops.states == ["landed", "bronze_appended", "reconciled"]
    n = len(split(data, fmt))
    assert out["bigquery"]["rows"] == n and out["rows"] == n
    table = CASES[case][3]
    if table:
        assert out["table"].endswith(f".{table}")
    else:
        assert out["era"] in ("era_2024", "era_2024_v2") and out["era_kind"] == "known"
    assert spark.table(ident_of("p.w." + out["table"])).where("_run_id = 'r1'").count() == n


@java
@pytest.mark.parametrize("env", ["jsonl", "x12"], indirect=True)
def test_tamper_drops_a_branch_row_quarantines(monkeypatch, env):
    spark, _data, u, _case = env
    ops = FakeOps().install(monkeypatch)
    real = bronze.branch_rows
    monkeypatch.setattr(cli.bronze, "branch_rows", lambda *a: real(*a)[1:])
    monkeypatch.setattr(cli.bronze, "publish", lambda *a: pytest.fail("published"))
    with pytest.raises(cli.ReconcileFail):
        cli.load({**CFG, "versions": VERSIONS}, u, "r1")
    assert ops.states == ["landed", "bronze_appended", "quarantined"]
    assert [q["reason"] for q in ops.quarantine] == ["RECONCILE_FAIL"]
    ident = ident_of("p.w." + ops.lifecycle[-1]["detail"]["table"])
    assert bronze.main_history_len(spark, ident) == 0 and spark.table(ident).count() == 0


@java
@pytest.mark.parametrize("env", ["jsonl_blank", "jsonl_badbyte"], indirect=True)
def test_blank_and_non_utf8_ndjson_through_load(monkeypatch, env):
    spark, _data, u, case = env
    ops = FakeOps().install(monkeypatch)
    out = cli.load({**CFG, "versions": VERSIONS}, u, "r1")
    d = ops.lifecycle[-1]["detail"]
    assert ops.states[-1] == "reconciled" and d["expected"] == d["actual"] == out["rows"] == 5 - (case == "jsonl_blank")
    got = spark.table(ident_of("p.w." + out["table"])).where("_run_id = 'r1'")
    if case == "jsonl_blank":
        assert sorted(r[0] for r in got.select("_line_ordinal").collect()) == [1, 5, 6, 7]
    else:
        bad = got.where("_line_ordinal = 2").first()
        assert bad["_raw_encoding"] == "base64" and bad["record"] is None
