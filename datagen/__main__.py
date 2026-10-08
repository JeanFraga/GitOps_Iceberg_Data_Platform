"""python -m datagen generate [--volume ci|full] | python -m datagen upload"""

from __future__ import annotations

import argparse
import subprocess
import sys

from datagen import config
from datagen.generate import Context, generate
from datagen.upload import UploadError, upload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m datagen", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate", help="write datagen/out/ (wiped first)")
    gen.add_argument("--volume", help="volume profile; default datagen.volume_profile")
    sub.add_parser("upload", help="land files and load mpi_eval.ground_truth")
    args = parser.parse_args(argv)
    cfg = config.load()
    try:
        if args.cmd == "generate":
            name, volume = config.resolve_volume(cfg, args.volume)
            ctx = Context(cfg["datagen"]["seed"], name, volume, config.marker_token())
            manifest = generate(ctx)
            for f in manifest["files"]:
                print(f"{f['path']}: {f['records']} records sha256={f['sha256']}")
        else:
            for line in upload(cfg):
                print(line)
    except (config.VolumeError, UploadError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
