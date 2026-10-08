"""Size and storage-cost estimate for a volume profile, and the NFR-1 budget headroom guard. CLI tools only."""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from datagen.generate import Context, generate

USD_PER_GB_MONTH = 0.020  # GCS Standard, us-east1
GB = 1024**3
CALIBRATION_RECORDS = 300


class EstimateError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Estimate:
    files: int
    bytes: int

    @property
    def usd_month(self) -> float:
        return storage_cost(self.bytes)


def storage_cost(nbytes: int) -> float:
    return nbytes / GB * USD_PER_GB_MONTH


def estimate(ctx: Context) -> Estimate:
    """Scale landing bytes of a tiny calibration generate (same seed, years, drift) to the profile size."""
    target = int(ctx.volume["records_per_file"])
    cal = min(CALIBRATION_RECORDS, target)
    cal_ctx = dataclasses.replace(ctx, volume={**ctx.volume, "records_per_file": cal}, cache={}, _built={})
    tmp = Path(tempfile.mkdtemp(prefix="datagen-cal-"))
    try:
        manifest = generate(cal_ctx, tmp / "out")
        size = sum((tmp / "out" / f["path"]).stat().st_size for f in manifest["files"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return Estimate(len(manifest["files"]), round(size * target / cal))


def landing_bytes(bucket: str, run: Runner) -> int:
    """Current landing usage via `gcloud storage du -s`; 0 when empty. Fails closed when unreadable."""
    res = run(["gcloud", "storage", "du", "-s", f"gs://{bucket}/"], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise EstimateError(f"cannot read landing usage for budget guard: {res.stderr.strip()}")
    if not res.stdout.strip():
        return 0
    try:
        return int(res.stdout.split()[0])
    except ValueError as exc:
        raise EstimateError(f"unexpected `gcloud storage du` output: {res.stdout.strip()!r}") from exc


def headroom(cfg: dict, run: Runner) -> float:
    """Budget minus the monthly storage cost of what landing already holds (no MTD spend via gcloud)."""
    used = landing_bytes(f"{cfg['project_id']}-landing", run)
    return float(cfg["budget"]["amount_usd"]) - storage_cost(used)
