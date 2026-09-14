"""OPZ: profile config loader.

Loads config/<profile>.toml and returns a normalized dict.

Normalization rules (backward compatible):
- broker.clientId  (camelCase) is always present
- broker.client_id (snake_case) is always present
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# IBKR client_id valid range (TWS/Gateway API spec)
_IBKR_CLIENT_ID_MIN = 0
_IBKR_CLIENT_ID_MAX = 32767

_IBKR_PROFILE_PORTS = {
    "dev": {"tws": 7497, "gateway": 4002},
    "paper": {"tws": 7497, "gateway": 4002},
    "live": {"tws": 7496, "gateway": 4001},
}


def expected_broker_port(profile: str, *, broker_kind: str = "tws") -> int:
    prof = (profile or "paper").strip().lower()
    if prof not in _IBKR_PROFILE_PORTS:
        prof = "paper"
    kind = (broker_kind or "tws").strip().lower()
    if kind not in {"tws", "gateway"}:
        raise ValueError(f"Unsupported broker_kind: {broker_kind!r}")
    return int(_IBKR_PROFILE_PORTS[prof][kind])


def describe_broker_port(port: int) -> Dict[str, Any]:
    p = int(port)
    if p == 7497:
        return {"label": "tws_paper", "transport": "tws", "trading_mode": "paper"}
    if p == 7496:
        return {"label": "tws_live", "transport": "tws", "trading_mode": "live"}
    if p == 4002:
        return {"label": "gateway_paper", "transport": "gateway", "trading_mode": "paper"}
    if p == 4001:
        return {"label": "gateway_live", "transport": "gateway", "trading_mode": "live"}
    if p == 4004:
        return {"label": "gateway_bridge", "transport": "gateway", "trading_mode": "paper"}
    return {"label": "custom", "transport": "custom", "trading_mode": "unknown"}


def broker_port_matches_profile(profile: str, port: int) -> bool:
    prof = (profile or "paper").strip().lower()
    expected_mode = "paper" if prof in {"dev", "paper"} else "live"
    meta = describe_broker_port(port)
    if meta["trading_mode"] == "unknown":
        return False
    return str(meta["trading_mode"]) == expected_mode

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _read_toml(path: Path) -> Dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid TOML root in {path}")
    return data


def _normalize_broker(cfg: Dict[str, Any], *, profile: str = "paper") -> None:
    broker = cfg.get("broker")
    if broker is None:
        broker = {}
        cfg["broker"] = broker
    if not isinstance(broker, dict):
        raise ValueError("config[broker] must be a table/dict")

    if broker.get("host") is None:
        broker["host"] = "127.0.0.1"
    if broker.get("port") is None:
        broker["port"] = expected_broker_port(profile, broker_kind="tws")

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

    # Bounds check — IBKR TWS/Gateway accepts client_id in [0, 32767]
    for _val, _name in ((camel_i, "clientId"), (snake_i, "client_id")):
        if isinstance(_val, int) and not (_IBKR_CLIENT_ID_MIN <= _val <= _IBKR_CLIENT_ID_MAX):
            logger.warning(
                "config broker.%s=%s fuori range IBKR [%d, %d] — connessione potrebbe fallire silenziosamente",
                _name, _val, _IBKR_CLIENT_ID_MIN, _IBKR_CLIENT_ID_MAX,
            )

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
    _normalize_broker(cfg, profile=profile)
    return cfg
