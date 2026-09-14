from __future__ import annotations

import json
import socket
from typing import Any, Optional

from execution.config_loader import describe_broker_port
from execution.ibkr_preflight import build_broker_profile_expectation
from execution.ibkr_tws import IbkrConnectivityError, IbkrDependencyError, run_f3_t1_probe


STANDARD_IBKR_PORTS = (7497, 7496, 4002, 4001)


def _scan_common_ibkr_ports(host: str, timeout_sec: float = 0.2) -> dict[str, Any]:
    host = str(host or "127.0.0.1")
    open_ports: list[dict[str, Any]] = []
    for port in STANDARD_IBKR_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(float(timeout_sec))
            rc = sock.connect_ex((host, int(port)))
            if rc == 0:
                meta = describe_broker_port(port)
                open_ports.append(
                    {
                        "port": int(port),
                        "label": str(meta["label"]),
                        "transport": str(meta["transport"]),
                        "trading_mode": str(meta["trading_mode"]),
                    }
                )
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return {
        "host": host,
        "tested_ports": list(STANDARD_IBKR_PORTS),
        "open_count": len(open_ports),
        "open_ports": open_ports,
    }


def _build_diagnostic_hints(expectation, port_scan: dict[str, Any], *, configured_host: str, configured_port: int) -> list[str]:
    hints: list[str] = []
    open_ports = port_scan.get("open_ports") or []
    open_port_numbers = {int(p.get("port")) for p in open_ports if p.get("port") is not None}

    if int(configured_port) in open_port_numbers:
        hints.append(
            f"TCP listener detected on configured port {configured_port}; if readiness still fails, verify TWS/Gateway API socket permissions and active login session"
        )
        return hints

    if not open_ports:
        hints.append(
            "No IBKR listener detected on standard local ports 7497/7496/4002/4001; start TWS or IB Gateway and enable API socket access"
        )
        hints.append(
            f"QOpz application start does not start the broker runtime; broker readiness requires a live TWS/Gateway listener on {configured_host}"
        )
        return hints

    target_mode = str(expectation.profile_target_mode)
    same_mode_ports = [p for p in open_ports if str(p.get("trading_mode")) == target_mode]
    if same_mode_ports:
        ports_text = ", ".join(f"{p['port']} ({p['label']})" for p in same_mode_ports)
        hints.append(
            f"Detected {target_mode} IBKR listener(s) on {ports_text}; configured port is {configured_port}, so align broker.port to the active endpoint"
        )
    else:
        ports_text = ", ".join(f"{p['port']} ({p['label']})" for p in open_ports)
        hints.append(
            f"Detected IBKR listener(s) on {ports_text}, but none match profile mode={target_mode}; verify you did not start a live endpoint for a paper profile or vice versa"
        )

    if expectation.expected_gateway_port in open_port_numbers and configured_port != expectation.expected_gateway_port:
        hints.append(
            f"Gateway listener appears active on {expectation.expected_gateway_port}; set broker.port={expectation.expected_gateway_port} if you intend to use IB Gateway for profile={expectation.profile}"
        )
    if expectation.expected_tws_port in open_port_numbers and configured_port != expectation.expected_tws_port:
        hints.append(
            f"TWS listener appears active on {expectation.expected_tws_port}; set broker.port={expectation.expected_tws_port} if you intend to use TWS for profile={expectation.profile}"
        )
    return hints


def _run_option_chain_smoke(*, host: str, port: int, client_id: int, symbol: str, timeout_sec: float = 2.0) -> dict[str, Any]:
    """Read-only option chain smoke probe.

    Connects to IBKR, qualifies the underlying, requests sec-def option params,
    and returns small metadata useful for readiness diagnostics.
    """
    try:
        from ib_insync import IB, Stock  # type: ignore
    except Exception as exc:  # pragma: no cover - guarded by caller/tests via patching
        raise IbkrDependencyError("MISSING_DEPENDENCY ib_insync") from exc

    ib = IB()
    try:
        ok = ib.connect(host, int(port), clientId=int(client_id), timeout=float(timeout_sec), readonly=True)
        if not ok:
            raise IbkrConnectivityError("IB_CONNECT_FALSE")

        underlying = Stock(str(symbol).upper(), "SMART", "USD")
        qualified = ib.qualifyContracts(underlying)
        if not qualified:
            raise IbkrConnectivityError(f"OPTION_CHAIN_UNDERLYING_QUALIFY_FAIL symbol={symbol}")
        stock = qualified[0]

        params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        if not params:
            raise IbkrConnectivityError(f"OPTION_CHAIN_EMPTY symbol={symbol}")

        expiries: set[str] = set()
        strikes: set[float] = set()
        exchanges: set[str] = set()
        trading_class: str | None = None
        multiplier: str | None = None
        for p in params:
            expiries.update(getattr(p, "expirations", []) or [])
            strikes.update(float(s) for s in (getattr(p, "strikes", []) or []) if s is not None)
            ex = getattr(p, "exchange", None)
            if ex:
                exchanges.add(str(ex))
            if trading_class is None:
                tc = getattr(p, "tradingClass", None)
                trading_class = str(tc) if tc else None
            if multiplier is None:
                m = getattr(p, "multiplier", None)
                multiplier = str(m) if m else None

        return {
            "ok": True,
            "symbol": stock.symbol,
            "con_id": int(getattr(stock, "conId", 0) or 0),
            "exchange_count": len(exchanges),
            "exchanges": sorted(exchanges)[:5],
            "expiries_count": len(expiries),
            "first_expiries": sorted(expiries)[:5],
            "strikes_count": len(strikes),
            "strike_min": min(strikes) if strikes else None,
            "strike_max": max(strikes) if strikes else None,
            "trading_class": trading_class,
            "multiplier": multiplier,
        }
    except IbkrDependencyError:
        raise
    except IbkrConnectivityError:
        raise
    except Exception as exc:
        raise IbkrConnectivityError(str(exc)) from exc
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass



def _run_readonly_readiness_probe(
    *,
    host: str,
    port: int,
    client_id: int,
    timeout_sec: float,
    account: Optional[str],
    symbol: str,
    include_option_chain: bool,
) -> dict[str, Any]:
    base = run_f3_t1_probe(
        host=host,
        port=port,
        client_id=client_id,
        timeout_sec=float(timeout_sec),
        tcp_precheck=True,
        readonly=True,
        account=account,
    )

    probes: dict[str, Any] = {
        "connectivity": {
            "ok": True,
            "host": base.host,
            "port": base.port,
            "client_id": base.client_id,
            "duration_sec": base.duration_sec,
            "note": base.note,
        },
        "account_summary": {
            "ok": True,
            "account": base.account,
            "summary_keys": sorted((base.summary_kv or {}).keys()),
            "net_liquidation": (base.summary_kv or {}).get("NetLiquidation"),
            "buying_power": (base.summary_kv or {}).get("BuyingPower"),
        },
        "positions": {
            "ok": True,
            "count": int(base.positions_count or 0),
        },
        "option_chain": None,
    }

    if include_option_chain:
        probes["option_chain"] = _run_option_chain_smoke(
            host=host,
            port=port,
            client_id=client_id,
            symbol=symbol,
            timeout_sec=float(timeout_sec),
        )

    return probes



def run_ibkr_readiness(
    *,
    profile: str = "paper",
    timeout_sec: float = 2.0,
    account: Optional[str] = None,
    symbol: str = "SPY",
    include_option_chain: bool = True,
) -> dict[str, Any]:
    expectation = build_broker_profile_expectation(profile)
    port_scan = _scan_common_ibkr_ports(expectation.configured_host, timeout_sec=min(max(float(timeout_sec), 0.05), 0.5))
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
        "hints": [],
        "probes": {
            "port_scan": port_scan,
        },
        "message": "broker readiness semantics OK" if expectation.port_matches_profile else "broker readiness semantics mismatch",
    }

    # Warn early if the configured port is not what appears active locally.
    open_port_numbers = {int(p["port"]) for p in port_scan.get("open_ports") or [] if p.get("port") is not None}
    if expectation.expected_gateway_port in open_port_numbers and expectation.configured_port != expectation.expected_gateway_port:
        result["warnings"].append(
            f"detected active listener on gateway port {expectation.expected_gateway_port} while configured broker.port={expectation.configured_port}"
        )
    if expectation.expected_tws_port in open_port_numbers and expectation.configured_port != expectation.expected_tws_port:
        result["warnings"].append(
            f"detected active listener on tws port {expectation.expected_tws_port} while configured broker.port={expectation.configured_port}"
        )

    try:
        probe_payload = _run_readonly_readiness_probe(
            host=expectation.configured_host,
            port=expectation.configured_port,
            client_id=expectation.configured_client_id,
            timeout_sec=float(timeout_sec),
            account=account,
            symbol=(symbol or "SPY").upper(),
            include_option_chain=bool(include_option_chain),
        )
        result["probes"].update(probe_payload)
        result["message"] = "broker readiness OK"
        result["ok"] = bool(result["ok"]) and True
        if expectation.configured_port not in open_port_numbers:
            # Extremely rare race, but keep payload explainable.
            result["warnings"].append(
                f"configured broker.port={expectation.configured_port} responded to probe but was not observed during local port scan"
            )
    except IbkrDependencyError as exc:
        result["ok"] = False
        result["probes"].update(
            {
                "connectivity": {"ok": False, "error_type": "dependency", "error": str(exc)},
                "account_summary": {"ok": False},
                "positions": {"ok": False},
                "option_chain": {"ok": False} if include_option_chain else None,
            }
        )
        result["warnings"].append("ib_insync missing: install requirements-broker-ib.txt before readiness probes")
        result["message"] = "broker readiness failed: dependency missing"
    except IbkrConnectivityError as exc:
        result["ok"] = False
        result["probes"].update(
            {
                "connectivity": {"ok": False, "error_type": "connectivity", "error": str(exc)},
                "account_summary": {"ok": False},
                "positions": {"ok": False},
                "option_chain": {"ok": False} if include_option_chain else None,
            }
        )
        result["hints"] = _build_diagnostic_hints(
            expectation,
            port_scan,
            configured_host=expectation.configured_host,
            configured_port=expectation.configured_port,
        )
        result["message"] = "broker readiness failed: connectivity error"

    return result



def readiness_to_json(
    *,
    profile: str = "paper",
    timeout_sec: float = 2.0,
    account: Optional[str] = None,
    symbol: str = "SPY",
    include_option_chain: bool = True,
) -> str:
    return json.dumps(
        run_ibkr_readiness(
            profile=profile,
            timeout_sec=timeout_sec,
            account=account,
            symbol=symbol,
            include_option_chain=include_option_chain,
        ),
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )
