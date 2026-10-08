"""AD-5 era routing on the committed samples, plus the drift_report path through load()."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

import ingestion.__main__ as cli
from config.fingerprint import LAYOUTS, fingerprint, fp8
from ingestion import bronze, eras
from ingestion.marker import drop_marker_line
from ingestion.records import split
from ingestion.tests.test_main import FakeOps, fake_gcloud

SAMPLES = Path(__file__).resolve().parents[2] / "datagen" / "samples"
MANIFEST = json.loads((SAMPLES / "manifest.json").read_text())
FORMATS = {"csv": "csv", "ndjson": "jsonl", "834": "x12", "835": "x12", "837": "x12"}


def layout(rel: str) -> tuple[str, list[str]]:
    data = (SAMPLES / rel).read_bytes()
    fmt = FORMATS[rel.rsplit(".", 1)[1]]
    text = drop_marker_line(split(data, "csv"))[0].raw.decode() if fmt == "csv" else data.decode()
    return fingerprint(text, fmt), LAYOUTS[fmt](text)


def schema_drift(rel: str) -> bool:
    return "_drift_" in rel.rsplit("/", 1)[1]


@pytest.mark.parametrize("f", [f for f in MANIFEST["files"] if not schema_drift(f["path"])], ids=lambda f: f["path"])
def test_non_drift_and_datadrift_samples_resolve_to_their_era(f):
    fp, cols = layout(f["path"])
    route = eras.resolve(f["source"], f["feed"], fp, cols)
    assert route.kind == "known"
    entry = eras.registry(f["source"])[f["feed"]][route.era]
    assert (entry["fingerprint"], entry["columns"]) == (fp, cols)
    label = (f.get("era") or "").lower()
    if label:
        assert label == route.era or label in entry.get("aliases", [])


def test_known_payer_b_members_is_era_2024():
    assert eras.resolve("payer_b", "members", *layout("payer_b/members/payer_b_members_2024.csv")).era == "era_2024"


def test_additive_superset_routes_to_base_era():
    fp, cols = layout("payer_a/pharmacy/payer_a_pharmacy_2024_drift_add_column.csv")
    assert eras.resolve("payer_a", "pharmacy", fp, cols) == eras.Route("era_2024", "additive", ["prior_auth_number"])


@pytest.mark.parametrize(
    ("source", "feed", "rel"),
    [
        ("payer_b", "members", "payer_b/members/payer_b_members_2024_drift_rename_column.csv"),
        ("provider_directory", "providers", "provider_directory/providers/providers_drift_remove_column.csv"),
        ("payer_a", "patient_unknown_feed", "payer_a/pharmacy/payer_a_pharmacy_2024.csv"),
    ],
)
def test_rename_remove_and_unknown_feed_route_unmapped(source, feed, rel):
    fp, cols = layout(rel)
    route = eras.resolve(source, feed, fp, cols)
    assert route == eras.Route(f"unmapped_{fp8(fp)}", "unmapped") and route.era.islower()


def test_reorder_routes_unmapped():
    _fp, cols = layout("payer_b/members/payer_b_members_2024.csv")
    reordered = [cols[1], cols[0], *cols[2:], "extra"]  # superset too, but base order is broken
    fp = fingerprint(",".join(reordered), "csv")
    assert eras.resolve("payer_b", "members", fp, reordered).kind == "unmapped"
    pure = [cols[1], cols[0], *cols[2:]]  # same columns, different order, nothing added
    assert eras.resolve("payer_b", "members", fingerprint(",".join(pure), "csv"), pure).kind == "unmapped"


def _registry(tmp_path, feeds: dict) -> Path:
    body = {"f": {e: {"fingerprint": fingerprint(",".join(c), "csv"), "columns": c} for e, c in feeds.items()}}
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(body))
    return tmp_path


def test_ambiguous_superset_picks_widest_era_or_unmapped_on_tie(tmp_path):
    d = _registry(tmp_path, {"narrow": ["a", "b"], "wide": ["a", "b", "c"]})
    cols = ["a", "b", "c", "d"]
    fp = fingerprint(",".join(cols), "csv")
    assert eras.resolve("s", "f", fp, cols, d) == eras.Route("wide", "additive", ["d"])
    d = _registry(tmp_path, {"x": ["a", "b"], "y": ["a", "c"]})
    cols = ["a", "b", "c"]
    assert eras.resolve("s", "f", fingerprint(",".join(cols), "csv"), cols, d).kind == "unmapped"


# --- load() through local Spark: schema evolution and drift_report rows -------------------------

VERSIONS = yaml.safe_load((SAMPLES.parents[1] / "versions.yaml").read_text())
CFG = {"project_id": "p", "cost": {"max_bytes_billed": 1}, "versions": VERSIONS}


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    if shutil.which("java") is None:
        pytest.skip("Java not installed")
    s = bronze.build_session(bronze.hadoop_catalog_conf(str(tmp_path_factory.mktemp("wh"))), VERSIONS)
    s.stop = lambda: None
    yield s
    type(s).stop(s)


def run_load(monkeypatch, spark, source, feed, rel, run_id, ops):
    data = (SAMPLES / rel).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    uri = f"gs://b/source={source}/feed={feed}/ingest_date=2026-10-08/sha256={sha}/x.csv"
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: spark)

    def count(_p, _c, ref, run):
        return {"rows": spark.table(f"{bronze.CATALOG}.{ref.split('.', 2)[2]}").where(f"_run_id = '{run}'").count(),
                "min_ordinal": 3}  # fmt: skip

    monkeypatch.setattr(cli, "bq_count", count)
    return cli.load(CFG, uri, run_id)


@pytest.fixture
def drift_rows(monkeypatch):
    rows = []
    monkeypatch.setattr(cli.drift, "record", lambda **kw: rows.append(kw))
    return rows


def test_additive_load_widens_table_and_reports_once(monkeypatch, spark, drift_rows):
    ident = f"{bronze.CATALOG}.bronze_payer_a.pharmacy__era_2024"
    spark.sql(f"DROP TABLE IF EXISTS {ident} PURGE")
    # FakeOps does not filter by file, so each file gets its own.
    base = "payer_a/pharmacy/payer_a_pharmacy_2024.csv"
    add = "payer_a/pharmacy/payer_a_pharmacy_2024_drift_add_column.csv"
    run_load(monkeypatch, spark, "payer_a", "pharmacy", base, "r1", FakeOps().install(monkeypatch))
    assert drift_rows == []
    ops = FakeOps().install(monkeypatch)
    out = run_load(monkeypatch, spark, "payer_a", "pharmacy", add, "r2", ops)
    assert out["table"] == "bronze_payer_a.pharmacy__era_2024" and out["era_kind"] == "additive"
    assert "prior_auth_number" in spark.table(ident).columns
    assert spark.table(ident).where("_run_id = 'r1' AND prior_auth_number IS NOT NULL").count() == 0
    assert spark.table(ident).where("_run_id = 'r2' AND prior_auth_number IS NOT NULL").count() > 0
    assert len(drift_rows) == 1
    row = drift_rows[0]
    assert (row["schema_era"], row["drift_kind"], row["detail"]["added_columns"]) == (
        "era_2024", "additive_columns", ["prior_auth_number"])  # fmt: skip
    assert ops.states[-1] == "reconciled"
    # A base-era file after the widening still loads (missing column written as NULL).
    unit_scale = "payer_a/pharmacy/payer_a_pharmacy_2024_datadrift_unit_scale.csv"
    run_load(monkeypatch, spark, "payer_a", "pharmacy", unit_scale, "r3", FakeOps().install(monkeypatch))
    ops.install(monkeypatch)
    # Reload of the additive file: skipped, no second drift row.
    again = run_load(monkeypatch, spark, "payer_a", "pharmacy", add, "r4", ops)
    assert again["skipped"] == "already_appended" and len(drift_rows) == 1


def test_unmapped_load_goes_to_unmapped_table_and_reports_once(monkeypatch, spark, drift_rows):
    rel = "payer_b/members/payer_b_members_2024_drift_rename_column.csv"
    fp, _ = layout(rel)
    ident = f"{bronze.CATALOG}.bronze_payer_b.members__unmapped_{fp8(fp)}"
    spark.sql(f"DROP TABLE IF EXISTS {ident} PURGE")
    ops = FakeOps().install(monkeypatch)
    out = run_load(monkeypatch, spark, "payer_b", "members", rel, "r1", ops)
    assert out["table"] == f"bronze_payer_b.members__unmapped_{fp8(fp)}" and spark.table(ident).count() > 0
    assert [(r["schema_era"], r["drift_kind"]) for r in drift_rows] == [(f"unmapped_{fp8(fp)}", "unmapped_era")]
    assert run_load(monkeypatch, spark, "payer_b", "members", rel, "r2", ops)["skipped"] == "already_appended"
    assert len(drift_rows) == 1


def test_quarantine_writes_no_drift_row(monkeypatch, spark, drift_rows):
    rel = "provider_directory/providers/providers_drift_remove_column.csv"
    ops = FakeOps().install(monkeypatch)
    monkeypatch.setattr(cli.bronze, "branch_rows", lambda *a: [])
    with pytest.raises(cli.ReconcileFail):
        run_load(monkeypatch, spark, "provider_directory", "providers", rel, "r1", ops)
    assert drift_rows == [] and ops.states[-1] == "quarantined"


def test_registry_rebind_then_reload_writes_nothing(monkeypatch):
    """After an AD-5 rebind the file routes to another era table; it must still be skipped."""
    rel = "payer_b/members/payer_b_members_2024_drift_rename_column.csv"
    fp, _ = layout(rel)
    seen = [{"state": "landed", "table": None},
            {"state": "reconciled", "table": f"bronze_payer_b.members__unmapped_{fp8(fp)}", "branch": "wap_x"}]  # fmt: skip
    ops = FakeOps(seen).install(monkeypatch)
    monkeypatch.setattr(cli.eras, "resolve", lambda *a: eras.Route("era_2025", "known"))  # the rebind
    monkeypatch.setattr(cli.bronze, "build_session", lambda *a: pytest.fail("Spark started"))
    monkeypatch.setattr(cli.drift, "record", lambda **kw: pytest.fail("drift row written"))
    data = (SAMPLES / rel).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(cli, "_gcloud", fake_gcloud(data))
    out = cli.load(CFG, f"gs://b/source=payer_b/feed=members/ingest_date=d/sha256={sha}/x.csv", "r9")
    assert out["skipped"] == "already_appended" and len(ops.lifecycle) == 2


def test_non_csv_is_refused_with_nonzero_exit(monkeypatch, capsys):
    cfg = {**CFG, "profile": "demo", "run": {"lock_ttl_minutes": 1}}
    monkeypatch.setattr(cli.yaml, "safe_load", lambda _: cfg)
    monkeypatch.setattr(cli.runner, "BigQueryBackend", lambda *a: cli.runner.FakeBackend())
    monkeypatch.setattr(cli, "_gcloud", lambda args: pytest.fail("object read"))
    uri = "gs://b/source=payer_a/feed=835/ingest_date=d/sha256=" + "0" * 64 + "/x.835"
    assert cli.main(["--profile", "demo", "--file", uri]) == 5
    last = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert last["error_type"] == "UnsupportedFormat"
