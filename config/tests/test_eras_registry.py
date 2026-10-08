"""Era registry validation (AD-5) under `make validate-config`."""

import shutil
import sys
from pathlib import Path

import yaml

REPO_CONFIG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_CONFIG))
import load
from test_load import _contract


def _with_eras(tmp_path, registry: dict | None = None):
    d = _contract(tmp_path)
    shutil.copytree(REPO_CONFIG / "eras", d / "eras")
    if registry is not None:
        (d / "eras" / "scratch.yaml").write_text(yaml.safe_dump(registry))
    return d


ENTRY = {"fingerprint": "a" * 64, "columns": ["x"]}


def test_committed_registries_validate(tmp_path, capsys):
    assert load.main(["--profile", "demo", "--validate-only"], _with_eras(tmp_path)) == 0


def test_uppercase_era_fails_naming_file_and_key(tmp_path, capsys):
    d = _with_eras(tmp_path, {"members": {"Era_2024": ENTRY}})
    assert load.main(["--profile", "demo", "--validate-only"], d) != 0
    err = capsys.readouterr().err
    assert "eras/scratch.yaml" in err and "members" in err and "Era_2024" in err


def test_repeated_fingerprint_within_feed_fails(tmp_path, capsys):
    d = _with_eras(tmp_path, {"members": {"era_a": ENTRY, "era_b": ENTRY}})
    assert load.main(["--profile", "demo", "--validate-only"], d) != 0
    assert "members.era_b" in capsys.readouterr().err


def test_short_fingerprint_and_missing_columns_fail(tmp_path, capsys):
    d = _with_eras(tmp_path, {"members": {"era_a": {"fingerprint": "abc"}}})
    assert load.main(["--profile", "demo", "--validate-only"], d) != 0
    err = capsys.readouterr().err
    assert "columns" in err and "abc" in err


def test_alias_colliding_with_era_or_other_alias_fails(tmp_path, capsys):
    other = {"fingerprint": "b" * 64, "columns": ["y"]}
    d = _with_eras(tmp_path, {"m": {"era_a": {**ENTRY, "aliases": ["era_b"]}, "era_b": other}})
    assert load.main(["--profile", "demo", "--validate-only"], d) != 0
    assert "alias era_b" in capsys.readouterr().err
    d2 = tmp_path / "two"
    d2.mkdir()
    d = _with_eras(d2, {"m": {"era_a": {**ENTRY, "aliases": ["x1"]}, "era_b": {**other, "aliases": ["x1"]}}})
    assert load.main(["--profile", "demo", "--validate-only"], d) != 0
    assert "alias x1" in capsys.readouterr().err
