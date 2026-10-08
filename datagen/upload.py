"""Upload generated output: landing files (AD-3/FR-5) and mpi_eval.ground_truth. CLI tools only."""

from __future__ import annotations

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


def upload_landing(manifest: dict, out: Path, bucket: str, ingest_date: str, run: Runner) -> list[str]:
    log = []
    for f in manifest["files"]:
        prefix = f"gs://{bucket}/source={f['source']}/feed={f['feed']}/"
        name = Path(f["path"]).name
        target = f"{prefix}ingest_date={ingest_date}/sha256={f['sha256']}/{name}"
        if _sha_landed(run, prefix, f["sha256"]):
            log.append(f"skip (already landed): {name}")
            continue
        res = run(
            ["gcloud", "storage", "cp", "--if-generation-match=0", str(out / f["path"]), target],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            if _sha_landed(run, prefix, f["sha256"]):  # lost a race to an identical upload
                log.append(f"skip (already landed): {name}")
                continue
            raise UploadError(f"upload failed for {name}: {res.stderr.strip()}")
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
    log = upload_landing(manifest, out, f"{project}-landing", ingest_date, run)
    n = load_ground_truth(manifest, out, project, cfg["cost"]["max_bytes_billed"], run)
    log.append(f"ground_truth: {n} row(s) for generator_seed {manifest['seed']}")
    return log
