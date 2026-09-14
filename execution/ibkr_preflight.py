from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from execution.config_loader import (
    broker_port_matches_profile,
    describe_broker_port,
    expected_broker_port,
    load_profile_config,
)
from execution.ibkr_tws import IbkrConnectivityError, IbkrDependencyError, run_f3_t1_probe


@dataclass(frozen=True)
class BrokerProfileExpectation:
    profile: str
    configured_host: str
    configured_port: int
    configured_client_id: int
    configured_port_label: str
    configured_port_trading_mode: str
    expected_tws_port: int
    expected_gateway_port: int
    profile_target_mode: str
    port_matches_profile: bool
    recommended_port: int
    recommended_port_label: str
    warnings: list[str]


def build_broker_profile_expectation(profile: str) -> BrokerProfileExpectation:
    prof = (profile or "paper").strip().lower()
    cfg = load_profile_config(prof)
    broker = cfg.get("broker", {}) or {}

    host = str(broker.get("host", "127.0.0.1"))
    port = int(broker.get("port", expected_broker_port(prof, broker_kind="tws")))
    client_id = int(broker.get("client_id", broker.get("clientId", 7)))

    port_meta = describe_broker_port(port)
    tws_port = expected_broker_port(prof, broker_kind="tws")
    gateway_port = expected_broker_port(prof, broker_kind="gateway")
    target_mode = "paper" if prof in {"dev", "paper"} else "live"

    warnings: list[str] = []
    if not broker_port_matches_profile(prof, port):
        warnings.append(
            f"configured broker.port={port} ({port_meta['label']}) does not match profile={prof}; expected {target_mode} semantics"
        )
    if prof == "dev" and port_meta.get("trading_mode") == "live":
        warnings.append("dev profile should not default to a live trading endpoint")

    recommended_port = tws_port
    recommended_label = describe_broker_port(recommended_port)["label"]

    return BrokerProfileExpectation(
        profile=prof,
        configured_host=host,
        configured_port=port,
        configured_client_id=client_id,
        configured_port_label=str(port_meta["label"]),
        configured_port_trading_mode=str(port_meta["trading_mode"]),
        expected_tws_port=tws_port,
        expected_gateway_port=gateway_port,
        profile_target_mode=target_mode,
        port_matches_profile=(len(warnings) == 0),
        recommended_port=recommended_port,
        recommended_port_label=recommended_label,
        warnings=warnings,
    )


def run_broker_preflight(
    *,
    profile: str = "paper",
    do_probe: bool = False,
    timeout_sec: float = 2.0,
    account: Optional[str] = None,
) -> dict[str, Any]:
    expectation = build_broker_profile_expectation(profile)

    result: dict[str, Any] = {
        "ok": expectation.port_matches_profile,
        "profile": expectation.profile,
        "configured": {
            "host": expectation.configured_host,
            "port": expectation.configured_port,
            "client_id": expectation.configured_client_id,
            "port_label": expectation.configured_port_label,
            "port_trading_mode": expectation.configured_port_trading_mode,
        },
        "expected": {
            "target_mode": expectation.profile_target_mode,
            "tws_port": expectation.expected_tws_port,
            "gateway_port": expectation.expected_gateway_port,
            "recommended_port": expectation.recommended_port,
            "recommended_port_label": expectation.recommended_port_label,
        },
        "warnings": list(expectation.warnings),
        "probe": None,
        "message": "broker profile semantics OK" if expectation.port_matches_profile else "broker profile semantics mismatch",
    }

    if not do_probe:
        return result

    try:
        probe = run_f3_t1_probe(
            host=expectation.configured_host,
            port=expectation.configured_port,
            client_id=expectation.configured_client_id,
            timeout_sec=float(timeout_sec),
            tcp_precheck=True,
            readonly=True,
            account=account,
        )
        result["probe"] = {
            "ok": True,
            "host": probe.host,
            "port": probe.port,
            "client_id": probe.client_id,
            "duration_sec": probe.duration_sec,
            "account": probe.account,
            "positions_count": probe.positions_count,
            "summary_keys": sorted((probe.summary_kv or {}).keys()),
            "note": probe.note,
        }
    except IbkrDependencyError as exc:
        result["ok"] = False
        result["probe"] = {
            "ok": False,
            "error_type": "dependency",
            "error": str(exc),
        }
        result["warnings"].append("ib_insync missing: install requirements-broker-ib.txt before broker probes")
        result["message"] = "broker probe failed: dependency missing"
    except IbkrConnectivityError as exc:
        result["ok"] = False
        result["probe"] = {
            "ok": False,
            "error_type": "connectivity",
            "error": str(exc),
        }
        result["message"] = "broker probe failed: connectivity error"

    return result


def preflight_to_json(*, profile: str = "paper", do_probe: bool = False, timeout_sec: float = 2.0) -> str:
    return json.dumps(
        run_broker_preflight(profile=profile, do_probe=do_probe, timeout_sec=timeout_sec),
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )
