"""I/O matrix for the full-volume landing path (story 9), with a fake gcloud/bq runner."""

import csv
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from datagen import config, estimate
from datagen.__main__ import run_full
from datagen.generate import Context, generate
from datagen.upload import upload

TOKEN = config.marker_token()
SMALL = {"records_per_file": 300, "years": 1}
CFG = {"project_id": "proj-x", "cost": {"max_bytes_billed": 1000}, "budget": {"amount_usd": 5}}


class FakeRun:
    """ls answers from `landed`; du answers `du_bytes`; cp records the object as landed."""

    def __init__(self, landed: str = "", du_bytes: int = 0):
        self.calls, self.landed, self.du_bytes = [], landed, du_bytes
        self.seen_files: list[Path] = []

    def __call__(self, args, **kw):
        import subprocess

        self.calls.append(args)
        if args[:3] == ["gcloud", "storage", "ls"]:
            hits = "".join(line + "\n" for line in self.landed.splitlines() if line.startswith(args[3][:-2]))
            return subprocess.CompletedProcess(args, 0 if hits else 1, hits, "")
        if args[:3] == ["gcloud", "storage", "du"]:
            return subprocess.CompletedProcess(args, 0, f"{self.du_bytes}  {args[-1]}\n", "")
        if args[:3] == ["gcloud", "storage", "cp"]:
            self.seen_files.append(Path(args[4]))
            self.landed += args[5] + "\n"
        return subprocess.CompletedProcess(args, 0, "", "")

    def cps(self):
        return [c for c in self.calls if c[:3] == ["gcloud", "storage", "cp"]]


def _ctx(volume=SMALL):
    return Context(20261008, "full", volume, TOKEN)


def _summary_bytes(text: str) -> int:
    line = next(line for line in text.splitlines() if line.startswith("summary:"))
    return int(line.split(", ")[1].split()[0])


def test_full_run_estimate_first_lands_and_cleans_up(capsys):
    run = FakeRun()
    assert run_full(_ctx(), CFG, force=False, run=run) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("estimate:")
    assert run.cps() and all(c[3] == "--if-generation-match=0" for c in run.cps())
    repo = config.REPO.resolve()
    tmp = Path(tempfile.gettempdir()).resolve()
    for p in run.seen_files:
        assert repo not in p.resolve().parents and tmp in p.resolve().parents
        assert not p.exists()  # temp copy deleted
    # summary bytes equal the sum of landed file sizes (recomputed from an identical generate)
    with tempfile.TemporaryDirectory() as d:
        m = generate(_ctx(), Path(d))
        expected = sum((Path(d) / f["path"]).stat().st_size for f in m["files"])
    assert _summary_bytes("\n".join(lines)) == expected
    assert f"summary: {len(run.cps())} file(s)" in lines[-1]


def test_rerun_skips_every_file(capsys):
    run = FakeRun()
    run_full(_ctx(), CFG, force=False, run=run)
    n = len(run.cps())
    capsys.readouterr()
    run_full(_ctx(), CFG, force=False, run=run)
    out = capsys.readouterr().out
    assert len(run.cps()) == n  # no new cp
    assert out.count("skip (already landed)") == n


def test_over_budget_refuses(capsys):
    run = FakeRun(du_bytes=300 * estimate.GB)  # 6 USD/month already > 5 USD budget
    assert run_full(_ctx(), CFG, force=False, run=run) == 1
    assert not run.cps()


def test_over_budget_refusal_message(capsys):
    run_full(_ctx(), CFG, force=False, run=FakeRun(du_bytes=300 * estimate.GB))
    err = capsys.readouterr().err
    assert "refusing upload" in err and "set FORCE=1" in err


def test_over_budget_forced(capsys):
    run = FakeRun(du_bytes=300 * estimate.GB)
    assert run_full(_ctx(), CFG, force=True, run=run) == 0
    assert "warning" in capsys.readouterr().err
    assert run.cps()


def test_env_profile_conflict_config_wins(capsys):
    cfg = {
        "datagen": {"volume_profile": "ci", "volume_profiles": {"ci": {"records_per_file": 5, "years": 1}, "full": {}}}
    }
    name, _ = config.resolve_volume(cfg, None, {"DATAGEN_VOLUME_PROFILE": "full"})
    assert name == "ci"
    assert "config wins" in capsys.readouterr().err


def test_env_fills_unset_key():
    cfg = {"datagen": {"volume_profile": "ci", "volume_profiles": {"ci": {"records_per_file": 5}}}}
    _, vol = config.resolve_volume(cfg, None, {"DATAGEN_YEARS": "2", "DATAGEN_RECORDS_PER_FILE": "9"})
    assert vol == {"records_per_file": 5, "years": 2}


def test_read_env_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# c\nexport DATAGEN_YEARS='3'\nOTHER=x\n")
    assert config.read_env(p, {"OTHER": "y"}) == {"DATAGEN_YEARS": "3", "OTHER": "y"}


def test_estimate_scales_with_records():
    small = estimate.estimate(_ctx({"records_per_file": 300, "years": 1}))
    big = estimate.estimate(_ctx({"records_per_file": 3000, "years": 1}))
    assert big.files == small.files and 9 * small.bytes < big.bytes < 11 * small.bytes


def test_ci_volume_about_5000_members(tmp_path):
    name, vol = config.resolve_volume(config.load(), "ci", {})
    generate(Context(20261008, name, vol, TOKEN), tmp_path)
    members = set()
    for path in (tmp_path / "landing" / "payer_b" / "members").glob("payer_b_members_*.csv"):
        members |= {r["member_id"] for r in csv.DictReader(path.read_text().splitlines()[1:])}
    assert 4500 <= len(members) <= 5500  # drift slices split the feed across files


def test_upload_summary_line(tmp_path):
    generate(_ctx(), tmp_path)
    log = upload(CFG, tmp_path, FakeRun(), ingest_date="2026-10-08")
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert log[-1].startswith(f"summary: {len(m['files'])} file(s)")


def test_headroom_fails_closed_when_landing_unreadable():
    def run(args, **_):
        return subprocess.CompletedProcess(args, 1, "", "denied")

    with pytest.raises(estimate.EstimateError):
        estimate.headroom(CFG, run)
