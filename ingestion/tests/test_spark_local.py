"""Local Spark 4.0 append into a Hadoop-catalog Iceberg table (no GCP)."""

import shutil
from datetime import UTC, datetime

import pytest
import yaml

from ingestion import bronze
from ingestion.marker import drop_marker_line
from ingestion.records import split
from ingestion.tests.test_records_marker import SAMPLE

pytestmark = pytest.mark.skipif(shutil.which("java") is None, reason="Java not installed")
VERSIONS = yaml.safe_load((SAMPLE.parents[4] / "versions.yaml").read_text())


def test_append_to_local_iceberg(tmp_path):
    cols, rows = bronze.build_rows(
        drop_marker_line(split(SAMPLE.read_bytes(), "csv")), ingested_at=datetime(2026, 10, 8, tzinfo=UTC),
        source_file="gs://b/x.csv", record_source="payer_b.members", sha256="0" * 64, run_id="r1",
    )  # fmt: skip
    spark = bronze.build_session(bronze.hadoop_catalog_conf(str(tmp_path)), VERSIONS)
    try:
        bronze.append(spark, "bronze_payer_b", "members__era_2024", cols, rows, "r1")
        bronze.append(spark, "bronze_payer_b", "members__era_2024", cols, [(*r[:-1], "r2") for r in rows[:5]], "r2")
        t = f"{bronze.CATALOG}.bronze_payer_b.members__era_2024"
        got = spark.sql(f"SELECT _run_id, count(*) n, min(_line_ordinal) m FROM {t} GROUP BY _run_id").collect()
        assert {(r["_run_id"], r["n"], r["m"]) for r in got} == {("r1", 720, 3), ("r2", 5, 3)}
        types = {f.name: f.dataType.simpleString() for f in spark.table(t).schema}
        assert all(types[c] == "string" for c in cols)
        part = spark.sql(f"SELECT * FROM {t}.partitions").count()
        assert part == 1
        snaps = spark.sql(f"SELECT summary['run_id'] AS r FROM {t}.snapshots").collect()
        assert [s["r"] for s in snaps] == ["r1", "r2"]
    finally:
        spark.stop()
