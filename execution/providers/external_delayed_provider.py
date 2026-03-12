from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from execution.market_provider_contract import IndexSnapshotRequest, OptionsChainRequest, UniverseSnapshotRequest
from ._row_utils import normalize_symbols, to_universe_row, utcnow_iso


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTERNAL_DELAYED_CSV = ROOT / "data" / "providers" / "external_delayed_quotes.csv"


class ExternalDelayedCsvProvider:
    provider_name = "external_delayed_csv"
    feed_mode = "delayed"

    def __init__(self, csv_path: Path | None = None):
        self.csv_path = csv_path or DEFAULT_EXTERNAL_DELAYED_CSV

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.csv_path.exists() or not self.csv_path.is_file():
            return []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]

    def get_universe_snapshot(self, req: UniverseSnapshotRequest) -> dict[str, Any]:
        symbols = set(normalize_symbols(req.symbols))
        out: list[dict[str, Any]] = []
        for row in self._read_rows():
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if symbols and symbol not in symbols:
                continue
            rec = {
                "asset_type": row.get("asset_type") or "equity",
                "last": row.get("last"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "iv": row.get("iv"),
                "open_interest": row.get("open_interest"),
                "volume": row.get("volume"),
                "delta": row.get("delta"),
                "gamma": row.get("gamma"),
                "theta": row.get("theta"),
                "vega": row.get("vega"),
                "rho": row.get("rho"),
                "underlying_price": row.get("underlying_price"),
                "observed_at_utc": row.get("observed_at_utc"),
            }
            parsed = to_universe_row(symbol, req.regime, rec)
            if parsed is not None:
                out.append(parsed)

        return {
            "provider": self.provider_name,
            "feed_mode": self.feed_mode,
            "generated_at_utc": utcnow_iso(),
            "source_channel": str(self.csv_path),
            "rows": out,
            "count": len(out),
        }

    def get_options_chain(self, req: OptionsChainRequest) -> dict[str, Any]:
        snap = self.get_universe_snapshot(UniverseSnapshotRequest(symbols=[req.symbol], regime="NORMAL"))
        rows = [r for r in snap.get("rows", []) if str(r.get("symbol", "")).upper() == req.symbol.upper()]
        return {
            "provider": self.provider_name,
            "feed_mode": self.feed_mode,
            "generated_at_utc": utcnow_iso(),
            "symbol": req.symbol.upper(),
            "expiry": req.expiry,
            "contracts": rows,
        }

    def get_index_snapshot(self, req: IndexSnapshotRequest) -> dict[str, Any]:
        snap = self.get_universe_snapshot(UniverseSnapshotRequest(symbols=req.symbols, regime="NORMAL"))
        rows = [r for r in snap.get("rows", []) if str(r.get("asset_type") or "").lower() in {"index", "etf", "equity"}]
        return {
            "provider": self.provider_name,
            "feed_mode": self.feed_mode,
            "generated_at_utc": utcnow_iso(),
            "rows": rows,
        }
