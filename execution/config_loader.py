"""OPZ: profile config loader.

Loads config/<profile>.toml and returns a normalized dict.

Normalization rules (backward compatible):
- broker.clientId  (camelCase) is always present
- broker.client_id (snake_case) is always present
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _read_toml(path: Path) -> Dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid TOML root in {path}")
    return data


def _normalize_broker(cfg: Dict[str, Any]) -> None:
    broker = cfg.get("broker")
    if broker is None:
        return
    if not isinstance(broker, dict):
        raise ValueError("config[broker] must be a table/dict")

    # Accept both spellings.
    camel = broker.get("clientId")
    snake = broker.get("client_id")

    # Derive missing values.
    if camel is None and snake is not None:
        camel = snake
    if snake is None and camel is not None:
        snake = camel

    # Default if still missing.
    if camel is None and snake is None:
        camel = 7
        snake = 7

    # Coerce to int if possible.
    try:
        camel_i = int(camel)
    except (ValueError, TypeError):
        camel_i = camel  # leave as-is (will surface downstream)
    try:
        snake_i = int(snake)
    except (ValueError, TypeError):
        snake_i = snake

    broker["clientId"] = camel_i
    broker["client_id"] = snake_i


def load_profile_config(profile: str, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load and normalize a profile config.

    Parameters
    ----------
    profile:
        e.g. "paper" or "live"
    repo_root:
        optional explicit repo root; defaults to 2 parents above this file.

    Returns
    -------
    dict
        normalized config dict
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]

    path = repo_root / "config" / f"{profile}.toml"
    if not path.exists():
        raise FileNotFoundError(str(path))

    cfg = _read_toml(path)
    _normalize_broker(cfg)
    return cfg
