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


def test_happy_path_writes_deterministic_resolved(tmp_path):
    d = _setup(tmp_path, "z: 1\nflags:\n  b: true\n  a: false\n", {"demo": "profile: demo\nregion: r1\n"})
    out = load.write_resolved("demo", d)
    first = out.read_text()
    assert first.startswith("# GENERATED")
    assert load.resolve("demo", d) == {"z": 1, "flags": {"a": False, "b": True}, "profile": "demo", "region": "r1"}
    body = first.splitlines()[1:]
    assert body[0] == "flags:" and body[1] == "  a: false"
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
