"""Bronze write-audit-publish (AD-4/AD-6): all-STRING columns plus lineage, one Iceberg table per (source, feed, era).

The SparkSession uses the BigLake Iceberg REST catalog; tests pass a Hadoop catalog instead.
Only appends to a WAP branch and fast-forwards main: no row rewrites, no snapshot expiry.
"""

from __future__ import annotations

import csv
from datetime import datetime

from ingestion.records import Record

REST_URI = "https://biglake.googleapis.com/iceberg/v1/restcatalog"
CATALOG = "bronze_cat"  # Spark-side alias; the BigLake catalog name is the warehouse bucket
LINEAGE = [
    ("_raw_line", "string"),
    ("_raw_encoding", "string"),
    ("_line_ordinal", "bigint"),
    ("_ingested_at", "timestamp"),
    ("_source_file", "string"),
    ("_record_source", "string"),
    ("_landed_sha256", "string"),  # not _file_*: BigQuery reserves that prefix and BigLake rejects it
    ("_run_id", "string"),
]


class BronzeError(Exception):
    pass


def rest_catalog_conf(project_id: str) -> dict[str, str]:
    p = f"spark.sql.catalog.{CATALOG}"
    return {
        p: "org.apache.iceberg.spark.SparkCatalog",
        f"{p}.type": "rest",
        f"{p}.uri": REST_URI,
        f"{p}.warehouse": f"gs://{project_id}-warehouse",
        f"{p}.header.x-goog-user-project": project_id,
        f"{p}.rest.auth.type": "org.apache.iceberg.gcp.auth.GoogleAuthManager",
        f"{p}.io-impl": "org.apache.iceberg.gcp.gcs.GCSFileIO",
        f"{p}.rest-metrics-reporting-enabled": "false",
    }


def hadoop_catalog_conf(warehouse: str) -> dict[str, str]:
    p = f"spark.sql.catalog.{CATALOG}"
    return {p: "org.apache.iceberg.spark.SparkCatalog", f"{p}.type": "hadoop", f"{p}.warehouse": warehouse}


def packages(versions: dict) -> str:
    pkgs = [versions["iceberg_spark_runtime"]]
    if versions.get("iceberg_gcp_bundle"):
        pkgs.append(versions["iceberg_gcp_bundle"])
    return ",".join(pkgs)


def build_session(catalog_conf: dict[str, str], versions: dict):
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.master("local[2]")
        .appName("bronze-loader")
        .config("spark.jars.packages", packages(versions))
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
    )
    for key, value in catalog_conf.items():
        builder = builder.config(key, value)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def build_rows(
    records: list[Record], *, ingested_at: datetime, source_file: str, record_source: str, sha256: str, run_id: str
) -> tuple[list[str], list[tuple]]:
    """Header record + data records -> (column names, rows). Values are kept as strings, never logged."""
    if not records:
        raise BronzeError("no header record after the marker line")
    header_rec, data = records[0], records[1:]
    if header_rec.encoding != "utf-8":
        raise BronzeError("header record is not UTF-8")
    header = next(csv.reader([header_rec.raw.decode("utf-8")]))
    columns = [h.strip().lower() for h in header]
    if len(set(columns)) != len(columns) or any(not c or c.startswith("_") for c in columns):
        raise BronzeError("header has empty, duplicate or reserved (_-prefixed) column names")
    rows = []
    for rec in data:
        if rec.encoding == "utf-8":
            fields = next(csv.reader([rec.raw.decode("utf-8")], strict=False), [])
            fields = (fields + [None] * len(columns))[: len(columns)]
        else:
            fields = [None] * len(columns)
        lineage = (rec.raw_line, rec.encoding, rec.ordinal, ingested_at, source_file, record_source, sha256, run_id)
        rows.append((*fields, *lineage))
    return columns, rows


def ragged_count(records: list[Record]) -> int:
    """Data records whose CSV field count differs from the header's (still loaded; counted only)."""
    if not records:
        return 0
    width = len(next(csv.reader([records[0].raw.decode("utf-8", errors="replace")])))
    return sum(
        len(next(csv.reader([rec.raw.decode("utf-8", errors="replace")], strict=False), [])) != width
        for rec in records[1:]
    )


def wap_branch(sha256: str) -> str:
    return f"wap_{sha256[:8]}"


def ensure_table(spark, namespace: str, table: str, columns: list[str]) -> str:
    """Create namespace/table if absent (partitioned by days(_ingested_at)). Returns the identifier."""
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.{namespace}")
    ident = f"{CATALOG}.{namespace}.{table}"
    ddl = ", ".join([f"`{c}` string" for c in columns] + [f"`{n}` {t}" for n, t in LINEAGE])
    spark.sql(f"CREATE TABLE IF NOT EXISTS {ident} ({ddl}) USING iceberg PARTITIONED BY (days(_ingested_at))")
    return ident


def main_snapshot_id(spark, ident: str) -> int | None:
    rows = spark.sql(f"SELECT snapshot_id FROM {ident}.refs WHERE name = 'main'").collect()
    return int(rows[0]["snapshot_id"]) if rows else None


def write_branch(
    spark, namespace: str, table: str, columns: list[str], rows: list[tuple], run_id: str, sha256: str
) -> tuple[str, str]:
    """AD-4 write step: (re)create wap_<sha8> at main's head and append this delivery to it.

    Returns (identifier, branch). Main is not touched.
    """
    from pyspark.sql.types import LongType, StringType, StructField, StructType, TimestampType

    types = {"string": StringType(), "bigint": LongType(), "timestamp": TimestampType()}
    schema = StructType(
        [StructField(c, StringType(), True) for c in columns] + [StructField(n, types[t], True) for n, t in LINEAGE]
    )
    ident = ensure_table(spark, namespace, table, columns)
    branch = wap_branch(sha256)
    # Resets a stale branch from an earlier failed attempt to main's head (or to an empty
    # snapshot when the table has none yet).
    if main_snapshot_id(spark, ident) is None:
        # No main head to replace from: drop a stale branch, then create it (empty snapshot).
        spark.sql(f"ALTER TABLE {ident} DROP BRANCH IF EXISTS `{branch}`")
        spark.sql(f"ALTER TABLE {ident} CREATE BRANCH `{branch}`")
    else:
        spark.sql(f"ALTER TABLE {ident} CREATE OR REPLACE BRANCH `{branch}`")
    df = spark.createDataFrame(rows, schema)
    (df.writeTo(f"{ident}.branch_{branch}")
       .option("snapshot-property.run_id", run_id)
       .option("snapshot-property.file_sha256", sha256)
       .append())  # fmt: skip
    return ident, branch


def branch_rows(spark, ident: str, branch: str, run_id: str) -> list[tuple[int, str | None, str | None]]:
    """(_line_ordinal, _raw_line, _raw_encoding) for this run on the branch. Values stay in memory, never logged."""
    df = spark.read.option("branch", branch).table(ident)
    got = df.where(df["_run_id"] == run_id).select("_line_ordinal", "_raw_line", "_raw_encoding").collect()
    return [(int(r[0]), r[1], r[2]) for r in got]


def publish(spark, ident: str, branch: str, run_id: str) -> int:
    """AD-4 publish: fast-forward main to the WAP branch. Returns the run's snapshot_id."""
    ns_tbl = ident.split(".", 1)[1]
    spark.sql(f"CALL {CATALOG}.system.fast_forward('{ns_tbl}', 'main', '{branch}')")
    return run_snapshot_id(spark, ident, run_id)


def run_snapshot_id(spark, ident: str, run_id: str) -> int:
    snap = spark.sql(
        f"SELECT snapshot_id FROM {ident}.snapshots WHERE summary['run_id'] = '{run_id}' "
        "ORDER BY committed_at DESC LIMIT 1"
    ).collect()
    if not snap:
        raise BronzeError("no snapshot tagged with this run_id")
    return int(snap[0]["snapshot_id"])


def published_snapshot(spark, ident: str, sha256: str) -> int | None:
    """A main-lineage snapshot already tagged with this file_sha256 (a publish whose `reconciled` was lost)."""
    rows = spark.sql(
        f"SELECT s.snapshot_id FROM {ident}.snapshots s JOIN {ident}.history h ON s.snapshot_id = h.snapshot_id "
        f"WHERE h.is_current_ancestor AND s.summary['file_sha256'] = '{sha256}' LIMIT 1"
    ).collect()
    return int(rows[0]["snapshot_id"]) if rows else None


def main_history_len(spark, ident: str) -> int:
    """Snapshots reachable from main (the main lineage)."""
    return spark.sql(f"SELECT count(*) n FROM {ident}.history WHERE is_current_ancestor").collect()[0]["n"]
