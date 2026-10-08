import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load


def _setup(tmp_path, defaults, profiles):
    (tmp_path / "profiles").mkdir()
    (tmp_path / "defaults.yaml").write_text(defaults)
    for name, body in profiles.items():
        (tmp_path / "profiles" / f"{name}.yaml").write_text(body)
    return tmp_path


REPO_CONFIG = Path(__file__).resolve().parent
VALID_DEFAULTS = (
    "flags:\n  workflows_enabled: false\n  composer_enabled: false\n"
    "  dataproc_schedule_enabled: false\n  ml_fallback_enabled: true\n"
    "drift:\n  data_drift_thresholds: null\n  mode: report_only\n"
    "budget:\n  amount_usd: 5\n  alert_thresholds: [0.5, 0.9, 1.0]\n"
    "run:\n  lock_ttl_minutes: 120\n"
    "datagen:\n  seed: 1\n  eval_seed: 2\n  volume_profile: ci\n  volume_profiles:\n"
    "    ci: {records_per_file: 1, years: 1}\n    full: {records_per_file: 2, years: 1}\n"
)
VALID_PROFILE = (
    "profile: demo\nproject_id: demo-project-1\nregion: us-east1\n"
    "billing_account: 000000-000000-000000\ncost:\n  max_bytes_billed: 1000\n"
)


def _contract(tmp_path, defaults=VALID_DEFAULTS, profile=VALID_PROFILE):
    """A config dir with the repo schema and a versions.yaml beside it."""
    (tmp_path / "config").mkdir()
    d = _setup(tmp_path / "config", defaults, {"demo": profile})
    shutil.copytree(REPO_CONFIG / "schemas", d / "schemas")
    shutil.copytree(REPO_CONFIG / "standards", d / "standards")
    (tmp_path / "versions.yaml").write_text('dataproc_runtime: "3.0"\n')
    return d


def test_happy_path_writes_deterministic_resolved(tmp_path):
    d = _contract(tmp_path)
    out = load.write_resolved("demo", d)
    first = out.read_text()
    assert first.startswith("# GENERATED")
    body = first.splitlines()[1:]
    top = [line.split(":")[0] for line in body if line and not line.startswith(" ")]
    assert top == sorted(top)
    assert body[body.index("drift:") + 1] == "  data_drift_thresholds: null"
    load.write_resolved("demo", d)
    assert out.read_text() == first


def test_missing_profile_exits_nonzero_and_writes_nothing(tmp_path, capsys):
    d = _setup(tmp_path, "a: 1\n", {})
    assert load.main(["--profile", "x"], d) != 0
    assert "x" in capsys.readouterr().err
    assert not (d / "resolved.yaml").exists()


def test_nested_merge(tmp_path):
    d = _setup(tmp_path, "flags:\n  a: false\n  b: true\n", {"p": "flags:\n  a: true\n"})
    assert load.resolve("p", d) == {"flags": {"a": True, "b": True}}


def test_versions_pins_resolved_under_versions_key(tmp_path):
    (tmp_path / "config").mkdir()
    d = _setup(tmp_path / "config", "a: 1\n", {"demo": "profile: demo\n"})
    (tmp_path / "versions.yaml").write_text('dataproc_runtime: "3.0"\n')
    assert load.resolve("demo", d)["versions"] == {"dataproc_runtime": "3.0"}


def test_repo_versions_yaml_is_resolved():
    resolved = load.resolve("demo")
    assert resolved["versions"]["dataproc_runtime"] == "3.0"
    assert resolved["versions"]["iceberg_spark_runtime"].endswith(":1.12.0")


def test_repo_profiles_validate():
    for profile in ("demo", "_template"):
        assert load.main(["--profile", profile, "--validate-only"]) == 0


def test_unknown_flag_key_fails_validation(tmp_path, capsys):
    d = _contract(tmp_path, profile=VALID_PROFILE + "flags:\n  looker_enabled: true\n")
    assert load.main(["--profile", "demo", "--validate-only"], d) == 1
    assert "looker_enabled" in capsys.readouterr().err


def test_unknown_top_level_key_fails_validation(tmp_path):
    d = _contract(tmp_path, profile=VALID_PROFILE + "surprise: 1\n")
    assert load.main(["--profile", "demo", "--validate-only"], d) == 1


def test_cost_flag_on_in_defaults_fails(tmp_path, capsys):
    d = _contract(tmp_path, defaults=VALID_DEFAULTS.replace("composer_enabled: false", "composer_enabled: true"))
    assert load.main(["--profile", "demo", "--validate-only"], d) == 1
    assert "composer_enabled" in capsys.readouterr().err


def test_ml_fallback_off_in_defaults_fails(tmp_path):
    d = _contract(tmp_path, defaults=VALID_DEFAULTS.replace("ml_fallback_enabled: true", "ml_fallback_enabled: false"))
    assert load.main(["--profile", "demo", "--validate-only"], d) == 1


def test_check_detects_hand_edit(tmp_path):
    d = _contract(tmp_path)
    assert load.main(["--profile", "demo", "--check"], d) == 1  # missing counts as stale
    load.write_resolved("demo", d)
    assert load.main(["--profile", "demo", "--check"], d) == 0
    out = d / "resolved.yaml"
    out.write_text(out.read_text().replace("us-east1", "us-west1"))
    assert load.main(["--profile", "demo", "--check"], d) == 1


def test_invalid_profile_does_not_write(tmp_path):
    d = _contract(tmp_path, profile="profile: demo\n")
    assert load.main(["--profile", "demo"], d) == 1
    assert not (d / "resolved.yaml").exists()


def test_cost_flag_on_in_defaults_blocks_write(tmp_path):
    d = _contract(tmp_path, defaults=VALID_DEFAULTS.replace("composer_enabled: false", "composer_enabled: true"))
    assert load.main(["--profile", "demo"], d) == 1
    assert not (d / "resolved.yaml").exists()


def test_repo_d7_drift_key_defaults_to_report_only():
    assert load.resolve("demo")["drift"] == {"data_drift_thresholds": None, "mode": "report_only"}


def test_unknown_lifecycle_state_fails_validation(tmp_path, capsys):
    d = _contract(tmp_path)
    path = d / "standards" / "lifecycle.yaml"
    path.write_text(path.read_text().replace("  - quarantined\n", "  - archived\n", 1))
    assert load.main(["--profile", "demo", "--validate-only"], d) == 1
    assert "lifecycle.yaml" in capsys.readouterr().err


def test_bytes_cap_set_passes(tmp_path):
    d = _contract(tmp_path)
    assert load.main(["--profile", "demo", "--check-bytes-cap"], d) == 0


def test_bytes_cap_missing_fixture_fails(capsys):
    fixture = REPO_CONFIG / "tests" / "fixtures" / "no_cap.yaml"
    assert load.main(["--profile", str(fixture), "--check-bytes-cap"]) == 1
    err = capsys.readouterr().err
    assert "no_cap.yaml" in err and "cost.max_bytes_billed" in err


def test_bytes_cap_zero_fails(tmp_path):
    d = _contract(tmp_path, profile=VALID_PROFILE.replace("1000", "0"))
    assert load.main(["--profile", "demo", "--check-bytes-cap"], d) == 1
