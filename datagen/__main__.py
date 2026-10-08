"""python -m datagen generate [--volume ci|full] [--eval] [--force] | python -m datagen upload

VOLUME=full generates to a temp dir outside the repo and lands it in gs://$PROJECT-landing/."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from datagen import config, data_drift, drift, estimate, noise
from datagen.generate import Context, generate
from datagen.upload import UploadError, upload

LANDED_VOLUMES = ("full",)  # generated outside the repo and streamed to landing


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
    args = parser.parse_args(argv)
    cfg = config.load()
    try:
        if args.cmd == "generate":
            name, volume = config.resolve_volume(cfg, args.volume, config.read_env())
            dg = cfg["datagen"]
            train_scenarios = noise.scenario_set(dg.get("eval_only_scenarios", []))
            ctx = Context(
                dg["eval_seed"] if args.eval else dg["seed"],
                name,
                volume,
                config.marker_token(),
                edge_case_rate=float(dg.get("edge_case_rate", 0.02)),
                scenarios=noise.scenario_set() if args.eval else train_scenarios,
                run="eval" if args.eval else "train",
                schema_drift=tuple(dg.get("schema_drift", [])),
                data_drift=tuple(dg.get("data_drift", [])),
            )
            if name in LANDED_VOLUMES:
                return run_full(ctx, cfg, args.force or bool(os.environ.get("FORCE")))
            manifest = generate(ctx)
            for f in manifest["files"]:
                print(f"{f['path']}: {f['records']} records sha256={f['sha256']}")
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
