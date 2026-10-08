"""python -m datagen generate [--volume ci|full] [--eval] [--force] | upload | samples

VOLUME=full generates to a temp dir outside the repo and lands it in gs://$PROJECT-landing/."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from datagen import config, data_drift, drift, estimate, noise
from datagen.generate import Context, generate
from datagen.upload import UploadError, upload

LANDED_VOLUMES = ("full",)  # generated outside the repo and streamed to landing
SAMPLES = Path(__file__).resolve().parent / "samples"


def _context(cfg: dict, name: str, volume: dict, eval_run: bool = False) -> Context:
    dg = cfg["datagen"]
    return Context(
        dg["eval_seed"] if eval_run else dg["seed"],
        name,
        volume,
        config.marker_token(),
        edge_case_rate=float(dg.get("edge_case_rate", 0.02)),
        scenarios=noise.scenario_set() if eval_run else noise.scenario_set(dg.get("eval_only_scenarios", [])),
        run="eval" if eval_run else "train",
        schema_drift=tuple(dg.get("schema_drift", [])),
        data_drift=tuple(dg.get("data_drift", [])),
    )


def sample_records(path: Path = config.GUARDRAILS) -> int:
    return int(yaml.safe_load(path.read_text())["repo_weight"]["sample_records"])


def _unland(value: str) -> str:
    return value.removeprefix("landing/")


def write_samples(cfg: dict, target: Path = SAMPLES) -> dict:
    """Sample-sized train run -> target/<source>/<feed>/*, ground_truth/, manifest.json (no names.txt)."""
    ctx = _context(cfg, "sample", {"records_per_file": sample_records(), "years": 1})
    tmp = Path(tempfile.mkdtemp(prefix="datagen-samples-"))
    try:
        out = tmp / "out"
        manifest = generate(ctx, out)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(out / "landing", target)
        shutil.copytree(out / "ground_truth", target / "ground_truth")
        for f in manifest["files"]:
            f["path"] = _unland(f["path"])
        for e in (*manifest["schema_drift"], *manifest["data_drift"]):
            e["file"] = _unland(e["file"])
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return manifest


def run_full(ctx: Context, cfg: dict, force: bool, run=subprocess.run) -> int:
    """Estimate -> budget guard -> generate to a temp dir outside the repo -> land -> summary -> cleanup."""
    est = estimate.estimate(ctx)
    room = estimate.headroom(cfg, run)
    print(
        f"estimate: {est.files} file(s), ~{est.bytes} bytes ({est.bytes / estimate.GB:.3f} GB), "
        f"~{est.usd_month:.4f} USD/month storage; budget headroom {room:.4f} USD",
        flush=True,
    )
    if est.usd_month > room:
        if not force:
            print("error: estimate exceeds budget headroom; refusing upload (set FORCE=1 to override)", file=sys.stderr)
            return 1
        print("warning: estimate exceeds budget headroom; FORCE=1 set, uploading anyway", file=sys.stderr)
    tmp = Path(tempfile.mkdtemp(prefix="datagen-full-"))
    try:
        out = tmp / "out"
        generate(ctx, out)
        for line in upload(cfg, out, run):
            print(line, flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m datagen", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate", help="write datagen/out/ (wiped first)")
    gen.add_argument("--volume", help="volume profile; default datagen.volume_profile")
    gen.add_argument("--eval", action="store_true", help="held-out eval run: datagen.eval_seed, all scenarios")
    gen.add_argument("--force", action="store_true", help="land even when the estimate exceeds budget headroom")
    sub.add_parser("upload", help="land files and load mpi_eval.ground_truth")
    sub.add_parser("samples", help="regenerate committed datagen/samples/ (repo_weight.sample_records per file)")
    args = parser.parse_args(argv)
    cfg = config.load()
    try:
        if args.cmd == "generate":
            name, volume = config.resolve_volume(cfg, args.volume, config.read_env())
            ctx = _context(cfg, name, volume, args.eval)
            if name in LANDED_VOLUMES:
                return run_full(ctx, cfg, args.force or bool(os.environ.get("FORCE")))
            manifest = generate(ctx)
            for f in manifest["files"]:
                print(f"{f['path']}: {f['records']} records sha256={f['sha256']}")
        elif args.cmd == "samples":
            totals: dict[str, int] = {}
            for f in write_samples(cfg)["files"]:
                key = f"{f['source']}/{f['feed']}"
                totals[key] = totals.get(key, 0) + f["records"]
            for key, n in sorted(totals.items()):
                print(f"{key}: {n} records")
        else:
            for line in upload(cfg):
                print(line)
    except (
        config.VolumeError,
        noise.ScenarioError,
        drift.DriftError,
        data_drift.DataDriftError,
        UploadError,
        estimate.EstimateError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
