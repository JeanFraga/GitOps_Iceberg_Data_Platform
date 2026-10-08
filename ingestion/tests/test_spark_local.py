"""Local Spark 4.0 write-audit-publish into a Hadoop-catalog Iceberg table (no GCP)."""

import hashlib
import shutil

import pytest
import yaml

import ingestion.__main__ as cli
from ingestion import bronze
from ingestion.tests.test_main import FakeOps, fake_gcloud
from ingestion.tests.test_records_marker import SAMPLE

pytestmark = pytest.mark.skipif(shutil.which("java") is None, reason="Java not installed")
VERSIONS = yaml.safe_load((SAMPLE.parents[4] / "versions.yaml").read_text())
IDENT = f"{bronze.CATALOG}.bronze_payer_b.members__era_2024"


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    s = bronze.build_session(bronze.hadoop_catalog_conf(str(tmp_path_factory.mktemp("wh"))), VERSIONS)
    s.stop = lambda: None  # load() stops its session; keep one per module
    yield s
    type(s).stop(s)


@pytest.fixture
def env(monkeypatch, spark):
    spark.sql(f"DROP TABLE IF EXISTS {IDENT} PURGE")  # test-only cleanup of the scratch Hadoop warehouse
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: spark)
    monkeypatch.setattr(cli, "bq_count", lambda p, c, ref, run: {
        "rows": spark.table(IDENT).where(f"_run_id = '{run}'").count(), "min_ordinal": 3})  # fmt: skip
    return spark, None


def land(monkeypatch, data):
    sha = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    return sha, f"gs://b/source=payer_b/feed=members/ingest_date=2026-10-08/sha256={sha}/x.csv"


def main_snapshots(spark):
    if not spark.catalog.tableExists(IDENT):
        return 0
    return bronze.main_history_len(spark, IDENT)


def test_pass_then_reload(monkeypatch, env):
    spark, _ = env
    sha, uri = land(monkeypatch, SAMPLE.read_bytes())
    ops = FakeOps().install(monkeypatch)
    out = cli.load({"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}, uri, "r1")
    assert ops.states == ["landed", "bronze_appended", "reconciled"]
    assert out["bigquery"]["rows"] == 720 and spark.table(IDENT).count() == 720
    assert main_snapshots(spark) == 1
    snap = spark.sql(f"SELECT summary FROM {IDENT}.snapshots WHERE snapshot_id = {out['snapshot_id']}").first()[0]
    assert snap["run_id"] == "r1" and snap["file_sha256"] == sha
    assert ops.lifecycle[-1]["detail"]["ragged_rows"] == 0
    out2 = cli.load({"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}, uri, "r2")
    assert out2["skipped"] == "already_appended" and len(ops.lifecycle) == 3
    assert spark.table(IDENT).count() == 720 and main_snapshots(spark) == 1


@pytest.mark.parametrize("tamper", ["count", "hash"])
def test_tamper_quarantines_and_leaves_main(monkeypatch, env, tamper):
    spark, _ = env
    _sha, uri = land(monkeypatch, SAMPLE.read_bytes())
    ops = FakeOps().install(monkeypatch)
    real = bronze.branch_rows

    def tampered(*a):
        rows = real(*a)
        if tamper == "count":
            return rows[1:]
        o, raw, enc = rows[5]
        return [*rows[:5], (o, raw + "x", enc), *rows[6:]]

    monkeypatch.setattr(cli.bronze, "branch_rows", tampered)
    monkeypatch.setattr(cli.bronze, "publish", lambda *a: pytest.fail("published"))
    with pytest.raises(cli.ReconcileFail):
        cli.load({"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}, uri, "r1")
    assert main_snapshots(spark) == 0 and spark.table(IDENT).count() == 0
    assert ops.states == ["landed", "bronze_appended", "quarantined"]
    assert [q["reason"] for q in ops.quarantine] == ["RECONCILE_FAIL"]
    d = ops.lifecycle[-1]["detail"]
    if tamper == "count":
        assert (d["expected"], d["actual"]) == (720, 719)
    else:
        assert d["mismatches"] == 1 and d["first_mismatch_ordinal"] == 8
        assert ops.quarantine[0]["line_ordinal"] == 8


def test_stale_branch_replaced_and_ragged_counted(monkeypatch, env):
    spark, _ = env
    data = SAMPLE.read_bytes() + b"M_RAGGED,only_two\n"
    _sha, uri = land(monkeypatch, data)
    ops = FakeOps().install(monkeypatch)
    cfg = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}
    real_publish = bronze.publish

    def crash(*a):
        raise RuntimeError("crash before fast-forward")

    monkeypatch.setattr(cli.bronze, "publish", crash)
    with pytest.raises(RuntimeError):
        cli.load(cfg, uri, "r1")
    assert main_snapshots(spark) == 0 and ops.states == ["landed", "bronze_appended"]
    monkeypatch.setattr(cli.bronze, "publish", real_publish)
    out = cli.load(cfg, uri, "r2")
    assert spark.table(IDENT).count() == 721 and out["bigquery"]["rows"] == 721
    assert spark.table(IDENT).where("_run_id = 'r1'").count() == 0
    assert out["ragged_rows"] == 1 and main_snapshots(spark) == 1
    assert ops.states == ["landed", "bronze_appended", "reconciled"]


def test_crash_after_fast_forward_is_recovered_not_republished(monkeypatch, env):
    spark, _ = env
    _sha, uri = land(monkeypatch, SAMPLE.read_bytes())
    ops = FakeOps().install(monkeypatch)
    cfg = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}
    real_publish = bronze.publish

    def publish_then_crash(*a):
        real_publish(*a)
        raise RuntimeError("crash after fast-forward")

    monkeypatch.setattr(cli.bronze, "publish", publish_then_crash)
    with pytest.raises(RuntimeError):
        cli.load(cfg, uri, "r1")
    monkeypatch.setattr(cli.bronze, "write_branch", lambda *a: pytest.fail("re-branched"))
    out = cli.load(cfg, uri, "r2")
    assert out["skipped"] == "already_published" and out["recovered"] == "published_without_reconciled"
    assert spark.table(IDENT).count() == 720 and main_snapshots(spark) == 1
    assert ops.states == ["landed", "bronze_appended", "reconciled"]
