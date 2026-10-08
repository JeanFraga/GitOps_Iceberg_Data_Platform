"""Single config entry point: config/resolved.yaml (config wins over .env) and the marker token."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RESOLVED = REPO / "config" / "resolved.yaml"
GUARDRAILS = REPO / "config" / "standards" / "guardrails.yaml"
ENV_FILE = REPO / ".env"
ENV_KEYS = {"DATAGEN_RECORDS_PER_FILE": "records_per_file", "DATAGEN_YEARS": "years"}


class VolumeError(ValueError):
    pass


def load(path: Path = RESOLVED) -> dict:
    return yaml.safe_load(path.read_text())


def marker_token(path: Path = GUARDRAILS) -> str:
    return yaml.safe_load(path.read_text())["synthetic_marker"]["token"]


def read_env(path: Path = ENV_FILE, environ: dict | None = None) -> dict[str, str]:
    """Simple KEY=VALUE `.env` merged under os.environ (process env wins over the file)."""
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.removeprefix("export ").split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    env.update(os.environ if environ is None else environ)
    return env


def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def resolve_volume(cfg: dict, override: str | None = None, env: dict | None = None) -> tuple[str, dict]:
    """Return (name, profile). Precedence: CLI override > config > .env (config wins on conflict;
    .env only fills keys config leaves unset)."""
    env = {} if env is None else env
    dg = cfg["datagen"]
    profiles = dg["volume_profiles"]
    env_name = env.get("DATAGEN_VOLUME_PROFILE")
    name = override or dg.get("volume_profile") or env_name
    if not override and env_name and dg.get("volume_profile") and env_name != dg["volume_profile"]:
        _warn(f"DATAGEN_VOLUME_PROFILE={env_name} ignored, config wins: {dg['volume_profile']}")
    if name not in profiles:
        raise VolumeError(f"unknown volume profile {name!r}; valid: {', '.join(sorted(profiles))}")
    profile = dict(profiles[name])
    for key, field in ENV_KEYS.items():
        if key not in env:
            continue
        if field in profile:
            if str(profile[field]) != env[key]:
                _warn(f"{key}={env[key]} ignored, config wins: {field}={profile[field]}")
        else:
            try:
                profile[field] = int(env[key])
            except ValueError as exc:
                raise VolumeError(f"{key} must be an integer, got {env[key]!r}") from exc
    return name, profile
