"""Single config entry point: config/resolved.yaml (config wins over .env) and the marker token."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RESOLVED = REPO / "config" / "resolved.yaml"
GUARDRAILS = REPO / "config" / "standards" / "guardrails.yaml"


class VolumeError(ValueError):
    pass


def load(path: Path = RESOLVED) -> dict:
    return yaml.safe_load(path.read_text())


def marker_token(path: Path = GUARDRAILS) -> str:
    return yaml.safe_load(path.read_text())["synthetic_marker"]["token"]


def resolve_volume(cfg: dict, override: str | None = None) -> tuple[str, dict]:
    """Return (name, profile); an explicit override wins over datagen.volume_profile."""
    profiles = cfg["datagen"]["volume_profiles"]
    name = override or cfg["datagen"]["volume_profile"]
    if name not in profiles:
        raise VolumeError(f"unknown volume profile {name!r}; valid: {', '.join(sorted(profiles))}")
    return name, profiles[name]
