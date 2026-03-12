from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from execution.market_provider_contract import IndexSnapshotRequest, OptionsChainRequest, UniverseSnapshotRequest
from .external_delayed_provider import ExternalDelayedCsvProvider
from .ibkr_provider import IbkrProvider
from ._row_utils import utcnow_iso


NUMERIC_FIELDS = [
    "last",
    "bid",
    "ask",
    "iv",
    "open_interest",
    "volume",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "underlying_price",
    "iv_rank",
    "spread_pct",
    "score",
    "regime_fit",
    "liquidity_score",
]


def _to_dt_utc(value: Any) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _freshness_seconds(value: Any, now: datetime) -> int | None:
    dt = _to_dt_utc(value)
    if dt is None:
        return None
    return max(0, int((now - dt).total_seconds()))


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


class ProviderRouter:
    policy_version = "v1"

    def __init__(self, ibkr: IbkrProvider | None = None, external: ExternalDelayedCsvProvider | None = None):
        self.ibkr = ibkr or IbkrProvider()
        self.external = external or ExternalDelayedCsvProvider()

    def _merge_rows(self, primary_rows: list[dict[str, Any]], fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        pmap = {str(r.get("symbol") or "").upper(): r for r in primary_rows if r.get("symbol")}
        fmap = {str(r.get("symbol") or "").upper(): r for r in fallback_rows if r.get("symbol")}
        symbols = sorted(set(pmap.keys()) | set(fmap.keys()))

        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            p = pmap.get(symbol)
            f = fmap.get(symbol)
            pf = _freshness_seconds((p or {}).get("observed_at_utc"), now)
            ff = _freshness_seconds((f or {}).get("observed_at_utc"), now)

            merged: dict[str, Any] = {
                "symbol": symbol,
                "asset_type": (p or f or {}).get("asset_type") or "equity",
                "strategy": (p or f or {}).get("strategy"),
                "observed_at_utc": (p or f or {}).get("observed_at_utc"),
                "freshness_s": pf if pf is not None else ff,
            }
            field_sources: dict[str, str] = {}
            conflict_flags: list[str] = []

            for fld in NUMERIC_FIELDS:
                pv = (p or {}).get(fld)
                fv = (f or {}).get(fld)

                chosen = None
                chosen_source = "none"
                if pv is not None and (pf is None or pf <= 300):
                    chosen = pv
                    chosen_source = self.ibkr.provider_name
                elif fv is not None and (ff is None or ff <= 1800):
                    chosen = fv
                    chosen_source = self.external.provider_name
                elif pv is not None:
                    chosen = pv
                    chosen_source = f"{self.ibkr.provider_name}:stale"
                elif fv is not None:
                    chosen = fv
                    chosen_source = f"{self.external.provider_name}:stale"

                merged[fld] = chosen
                field_sources[fld] = chosen_source

                pnum = _num(pv)
                fnum = _num(fv)
                if pnum is not None and fnum is not None:
                    tol = 0.01 if fld in {"last", "bid", "ask", "underlying_price"} else 0.10
                    base = max(abs(pnum), abs(fnum), 1e-9)
                    if abs(pnum - fnum) / base > tol:
                        conflict_flags.append(fld)

            merged["field_sources"] = field_sources
            merged["conflict_flags"] = sorted(set(conflict_flags))
            if p and f:
                merged["source"] = "mixed"
            elif p:
                merged["source"] = self.ibkr.provider_name
            elif f:
                merged["source"] = self.external.provider_name
            else:
                merged["source"] = "none"

            rows.append(merged)

        return rows

    def get_universe_snapshot(self, req: UniverseSnapshotRequest) -> dict[str, Any]:
        p = self.ibkr.get_universe_snapshot(req)
        f = self.external.get_universe_snapshot(req)
        rows = self._merge_rows(
            list(p.get("rows") or []),
            list(f.get("rows") or []),
        )
        return {
            "generated_at_utc": utcnow_iso(),
            "policy_version": self.policy_version,
            "source": "provider_router",
            "primary_provider": self.ibkr.provider_name,
            "fallback_provider": self.external.provider_name,
            "primary_count": int(p.get("count") or 0),
            "fallback_count": int(f.get("count") or 0),
            "rows": rows,
            "provider_debug": {
                "primary": p,
                "fallback": f,
            },
        }

    def get_options_chain(self, req: OptionsChainRequest) -> dict[str, Any]:
        p = self.ibkr.get_options_chain(req)
        f = self.external.get_options_chain(req)
        return {
            "generated_at_utc": utcnow_iso(),
            "source": "provider_router",
            "primary_provider": self.ibkr.provider_name,
            "fallback_provider": self.external.provider_name,
            "symbol": req.symbol.upper(),
            "expiry": req.expiry,
            "primary_contracts": p.get("contracts", []),
            "fallback_contracts": f.get("contracts", []),
        }

    def get_index_snapshot(self, req: IndexSnapshotRequest) -> dict[str, Any]:
        p = self.ibkr.get_index_snapshot(req)
        f = self.external.get_index_snapshot(req)
        rows = self._merge_rows(list(p.get("rows") or []), list(f.get("rows") or []))
        return {
            "generated_at_utc": utcnow_iso(),
            "source": "provider_router",
            "primary_provider": self.ibkr.provider_name,
            "fallback_provider": self.external.provider_name,
            "rows": rows,
        }
