from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
from typing import Any

from execution.market_provider_contract import IndexSnapshotRequest, OptionsChainRequest, UniverseSnapshotRequest
from ._row_utils import normalize_symbols, to_universe_row, utcnow_iso


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DB_PATH = ROOT / "data" / "demo_pipeline" / "index.duckdb"
PIPELINE_DATASET_DIR = ROOT / "data" / "demo_pipeline" / "datasets"


class IbkrProvider:
    provider_name = "ibkr_pipeline"
    feed_mode = "realtime"

    def _duckdb_module(self) -> Any | None:
        try:
            return importlib.import_module("duckdb")
        except ModuleNotFoundError:
            return None

    def _load_record_from_output(self, output_path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        rec = payload.get("record")
        return rec if isinstance(rec, dict) else None

    def _load_from_pipeline_duckdb(self, symbols: list[str], regime: str) -> list[dict[str, Any]]:
        if not PIPELINE_DB_PATH.exists():
            return []
        duckdb = self._duckdb_module()
        if duckdb is None:
            return []

        symbol_set = {s.upper() for s in symbols}
        con = duckdb.connect(str(PIPELINE_DB_PATH), read_only=True)
        rows = con.execute(
            """
            SELECT c.symbol, c.page_type, c.captured_ts_utc, e.output_path
            FROM captures c
            JOIN extractions e ON e.capture_id = c.id
            WHERE e.status = 'VALID'
            ORDER BY c.id DESC
            LIMIT 50000
            """
        ).fetchall()
        con.close()

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_symbol, page_type, captured_ts_utc, output_path in rows:
            symbol = str(raw_symbol or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            if symbol_set and symbol not in symbol_set:
                continue

            ptype = str(page_type or "").strip().lower()
            if ptype and ptype not in {"quote", "scanner", "snapshot", "summary", "optionchain", "option_chain"}:
                continue

            op = Path(str(output_path or "").strip())
            if not op.exists() or not op.is_file():
                continue

            rec = self._load_record_from_output(op)
            if not rec:
                continue
            rec["captured_ts_utc"] = str(captured_ts_utc or "")
            row = to_universe_row(symbol, regime, rec)
            if row is None:
                continue
            seen.add(symbol)
            out.append(row)
        return out

    def _latest_dataset_csv(self) -> Path | None:
        if not PIPELINE_DATASET_DIR.exists():
            return None
        csvs = [p for p in PIPELINE_DATASET_DIR.glob("*.csv") if p.is_file()]
        if not csvs:
            return None
        csvs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0]

    def _load_from_dataset_csv(self, symbols: list[str], regime: str) -> list[dict[str, Any]]:
        csv_path = self._latest_dataset_csv()
        if csv_path is None:
            return []
        symbol_set = {s.upper() for s in symbols}
        latest_by_symbol: dict[str, dict[str, Any]] = {}

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                source = str(row.get("source") or "").strip().lower()
                if source and source not in {"ibkr", "ibkr_demo", "ibkr_api"}:
                    continue
                symbol = str(row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                if symbol_set and symbol not in symbol_set:
                    continue

                capture_id = int(float(str(row.get("capture_id") or "0"))) if str(row.get("capture_id") or "").strip() else 0
                prev = latest_by_symbol.get(symbol)
                prev_capture = int(float(str(prev.get("capture_id") or "0"))) if prev else -1
                if prev is None or capture_id >= prev_capture:
                    latest_by_symbol[symbol] = dict(row)

        out: list[dict[str, Any]] = []
        for symbol, row in latest_by_symbol.items():
            rec = {
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": row.get("last"),
                "iv": row.get("iv"),
                "delta": row.get("delta"),
                "underlying_price": row.get("underlying_price"),
                "volume": row.get("volume"),
                "open_interest": row.get("open_interest"),
                "asset_type": row.get("asset_type") or "equity",
                "observed_at_utc": row.get("observed_ts_utc") or row.get("captured_ts_utc"),
            }
            parsed = to_universe_row(symbol, regime, rec)
            if parsed is not None:
                out.append(parsed)
        return out

    def get_universe_snapshot(self, req: UniverseSnapshotRequest) -> dict[str, Any]:
        symbols = normalize_symbols(req.symbols)
        rows = self._load_from_pipeline_duckdb(symbols, req.regime)
        source = "duckdb"
        if not rows:
            rows = self._load_from_dataset_csv(symbols, req.regime)
            source = "dataset_csv"

        return {
            "provider": self.provider_name,
            "feed_mode": self.feed_mode,
            "generated_at_utc": utcnow_iso(),
            "source_channel": source,
            "rows": rows,
            "count": len(rows),
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
