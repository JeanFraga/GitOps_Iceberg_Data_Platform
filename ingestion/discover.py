"""Batch discovery: `gcloud storage ls` on the landing bucket joined against ops.file_lifecycle by object_uri.

Never lists the catalog or Iceberg tables. Pending = an AD-3 object with no lifecycle row, or whose rows
are all `landed` (a later state, including rejected_duplicate, is terminal for discovery).
"""

from __future__ import annotations

import re
import subprocess

from ingestion import lifecycle

URI_RE = re.compile(r"^gs://[^/]+/source=(?P<source>[^/]+)/feed=(?P<feed>[^/]+)/.*?sha256=(?P<sha>[0-9a-f]{64})/[^/]+$")


def list_landing(bucket: str, run=None) -> list[str]:
    run = run or subprocess.run
    res = run(["gcloud", "storage", "ls", f"gs://{bucket}/**"], check=True, capture_output=True, text=True)
    return sorted(u.strip() for u in res.stdout.splitlines() if URI_RE.match(u.strip()))


def pending(project_id: str, max_bytes_billed: int, bucket: str, run=None) -> list[tuple[str, bool]]:
    """[(uri, has_rows)] in listing order; has_rows tells the caller whether `landed` is already recorded."""
    uris = list_landing(bucket, run)
    rows = lifecycle.rows_for_uris(
        project_id=project_id, max_bytes_billed=max_bytes_billed, uris=uris, run=run or subprocess.run
    )
    return [(u, u in rows) for u in uris if all(s == "landed" for s in rows.get(u, []))]
