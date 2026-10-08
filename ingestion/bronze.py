"""Bronze append (AD-4/AD-6): all-STRING columns plus lineage, one Iceberg table per (source, feed, era).

The SparkSession uses the BigLake Iceberg REST catalog; tests pass a Hadoop catalog instead.
Only appends: no update, delete or expire_snapshots.
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


def append(spark, namespace: str, table: str, columns: list[str], rows: list[tuple], run_id: str) -> int:
    """Create namespace/table if absent (partitioned by days(_ingested_at)) and append. Returns snapshot_id."""
    from pyspark.sql.types import LongType, StringType, StructField, StructType, TimestampType

    types = {"string": StringType(), "bigint": LongType(), "timestamp": TimestampType()}
    schema = StructType(
        [StructField(c, StringType(), True) for c in columns] + [StructField(n, types[t], True) for n, t in LINEAGE]
    )
    df = spark.createDataFrame(rows, schema)
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {CATALOG}.{namespace}")
    ident = f"{CATALOG}.{namespace}.{table}"
    # Explicit CREATE (schema fixed by the header + LINEAGE), then a plain append.
    ddl = ", ".join([f"`{c}` string" for c in columns] + [f"`{n}` {t}" for n, t in LINEAGE])
    spark.sql(f"CREATE TABLE IF NOT EXISTS {ident} ({ddl}) USING iceberg PARTITIONED BY (days(_ingested_at))")
    df.writeTo(ident).option("snapshot-property.run_id", run_id).append()
    snap = spark.sql(
        f"SELECT snapshot_id FROM {ident}.snapshots WHERE summary['run_id'] = '{run_id}' "
        "ORDER BY committed_at DESC LIMIT 1"
    ).collect()
    if not snap:
        raise BronzeError("no snapshot tagged with this run_id")
    return int(snap[0]["snapshot_id"])
