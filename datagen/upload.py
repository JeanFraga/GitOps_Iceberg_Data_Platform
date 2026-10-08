"""Upload generated output: landing files (AD-3/FR-5) and mpi_eval.ground_truth. CLI tools only."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from datagen.generate import OUT

Runner = Callable[..., subprocess.CompletedProcess]


class UploadError(RuntimeError):
    pass


def _sha_landed(run: Runner, prefix: str, sha: str) -> bool:
    res = run(["gcloud", "storage", "ls", f"{prefix}**"], capture_output=True, text=True, check=False)
    return res.returncode == 0 and f"/sha256={sha}/" in res.stdout


LANDED, REJECTED_OVERWRITE = "landed", "rejected_overwrite"


def landing_uri(bucket: str, source: str, feed: str, ingest_date: str, sha: str, name: str) -> str:
    """AD-3 landing path: source=/feed=/ingest_date=/sha256=/<name>."""
    return f"gs://{bucket}/source={source}/feed={feed}/ingest_date={ingest_date}/sha256={sha}/{name}"


def land_file(
    path: Path, source: str, feed: str, bucket: str, ingest_date: str, run: Runner, sha: str | None = None
) -> tuple[str, str]:
    """cp --if-generation-match=0 one file to its AD-3 path; no sha pre-skip.

    Returns (LANDED | REJECTED_OVERWRITE, target). An existing object is never replaced.
    """
    sha = sha or hashlib.sha256(path.read_bytes()).hexdigest()
    target = landing_uri(bucket, source, feed, ingest_date, sha, path.name)
    res = run(["gcloud", "storage", "cp", "--if-generation-match=0", str(path), target],
              capture_output=True, text=True, check=False)  # fmt: skip
    if res.returncode == 0:
        return LANDED, target
    if "412" in (res.stderr or "") or "precondition" in (res.stderr or "").lower():
        return REJECTED_OVERWRITE, target
    raise UploadError(f"upload failed for {path.name}: {(res.stderr or '').strip()}")


def upload_landing(
    manifest: dict, out: Path, bucket: str, ingest_date: str, run: Runner, totals: dict | None = None
) -> list[str]:
    """Land each file once; `totals` (if given) accumulates file count and local bytes landed or present."""
    log = []
    totals = {} if totals is None else totals
    totals.setdefault("files", 0)
    totals.setdefault("bytes", 0)
    for f in manifest["files"]:
        totals["files"] += 1
        totals["bytes"] += (out / f["path"]).stat().st_size
        prefix = f"gs://{bucket}/source={f['source']}/feed={f['feed']}/"
        name = Path(f["path"]).name
        if _sha_landed(run, prefix, f["sha256"]):
            log.append(f"skip (already landed): {name}")
            continue
        err: UploadError | None = None
        try:
            status, target = land_file(out / f["path"], f["source"], f["feed"], bucket, ingest_date, run, f["sha256"])
        except UploadError as exc:
            status, target, err = REJECTED_OVERWRITE, "", exc
        if status != LANDED:
            if _sha_landed(run, prefix, f["sha256"]):  # lost a race to an identical upload
                log.append(f"skip (already landed): {name}")
                continue
            raise err or UploadError(f"upload failed for {name}: precondition failed")
        log.append(f"landed: {target}")
    return log


def load_ground_truth(manifest: dict, out: Path, project: str, cap: int, run: Runner) -> int:
    path = out / "ground_truth" / "person_truth.jsonl"
    rows = [r for r in map(json.loads, path.read_text().splitlines()) if len(r) > 1]
    seed = int(manifest["seed"])
    bq = ["bq", f"--project_id={project}"]
    run(
        [*bq, "query", "--use_legacy_sql=false", f"--maximum_bytes_billed={cap}", "--quiet",
         f"DELETE FROM mpi_eval.ground_truth WHERE generator_seed = {seed}"],
        check=True,
    )  # fmt: skip
    if rows:
        run(
            [*bq, "load", "--source_format=NEWLINE_DELIMITED_JSON", "--ignore_unknown_values",
             "mpi_eval.ground_truth", str(path)],
            check=True,
        )  # fmt: skip
    return len(rows)


def upload(cfg: dict, out: Path = OUT, run: Runner = subprocess.run, ingest_date: str | None = None) -> list[str]:
    manifest_path = out / "manifest.json"
    if not manifest_path.exists():
        raise UploadError(f"{manifest_path} missing: run make generate first")
    manifest = json.loads(manifest_path.read_text())
    ingest_date = ingest_date or datetime.now(UTC).date().isoformat()
    project = cfg["project_id"]
    totals: dict = {}
    log = upload_landing(manifest, out, f"{project}-landing", ingest_date, run, totals)
    n = load_ground_truth(manifest, out, project, cfg["cost"]["max_bytes_billed"], run)
    log.append(f"ground_truth: {n} row(s) for generator_seed {manifest['seed']}")
    log.append(f"summary: {totals['files']} file(s), {totals['bytes']} bytes landed or already present")
    return log
