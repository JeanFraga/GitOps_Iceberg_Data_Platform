"""Land a local directory under AD-3: SRC/<source>/<feed>/<file> -> source=/feed=/ingest_date=/sha256=/<name>.

Reuses datagen.upload.land_file (cp --if-generation-match=0). An existing object is never replaced:
a collision logs land_rejected_overwrite and the other files continue.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from datagen.upload import LANDED, UploadError, land_file

Log = Callable[..., None]


def land_dir(src: Path, bucket: str, ingest_date: str, log: Log, run=subprocess.run) -> dict:
    """Returns {"landed": [uri], "rejected_overwrite": [uri], "failed": [path]}. Dot-files are skipped."""
    if not src.is_dir():
        raise FileNotFoundError(f"SRC is not a directory: {src}")
    out: dict[str, list[str]] = {"landed": [], "rejected_overwrite": [], "failed": []}
    files = (p for p in src.glob("*/*/*") if p.is_file())
    for path in sorted(p for p in files if not any(part.startswith(".") for part in p.relative_to(src).parts)):
        feed_dir = path.parent
        source, feed = feed_dir.parent.name, feed_dir.name
        try:
            status, uri = land_file(path, source, feed, bucket, ingest_date, run)
        except UploadError:
            out["failed"].append(str(path.relative_to(src)))
            log("land_failed", path=str(path.relative_to(src)))  # no stderr: keep the line value-free
            continue
        if status == LANDED:
            out["landed"].append(uri)
            log("land_landed", uri=uri)
        else:
            out["rejected_overwrite"].append(uri)
            log("land_rejected_overwrite", uri=uri)
    return out
