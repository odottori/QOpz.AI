from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = ROOT / "docs" / "IBKE setting decriptato.sanitized.xml"


def _is_simple_symbol(s: str) -> bool:
    if not s:
        return False
    t = s.strip().upper()
    if not t:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return all(ch in allowed for ch in t)


def extract_ibkr_universe_context(settings_path: str | None = None) -> dict[str, Any]:
    path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH
    out: dict[str, Any] = {
        "source": "ibkr_settings",
        "settings_path": str(path),
        "settings_exists": path.exists(),
        "symbols": [],
        "quote_symbol_count": 0,
        "pages": [],
        "scanners": [],
    }
    if not path.exists():
        return out

    tree = ET.parse(path)
    root = tree.getroot()

    # Quote universe
    quote_nodes = root.findall(".//QuoteElement")
    symbols_all: list[str] = []
    symbols_smart: list[str] = []
    seen_all: set[str] = set()
    seen_smart: set[str] = set()
    for q in quote_nodes:
        symbol = (q.get("symbol") or "").strip().upper()
        exch = (q.get("exchange") or "").strip().upper()
        if not _is_simple_symbol(symbol):
            continue
        if symbol not in seen_all:
            seen_all.add(symbol)
            symbols_all.append(symbol)
        if exch == "SMART" and symbol not in seen_smart:
            seen_smart.add(symbol)
            symbols_smart.append(symbol)

    symbols = symbols_smart if len(symbols_smart) >= 8 else symbols_all
    out["symbols"] = symbols
    out["quote_symbol_count"] = len(symbols)

    # Workspace pages
    pages: list[str] = []
    seen_pages: set[str] = set()
    for p in root.findall(".//TickerPageSetting"):
        name = (p.get("name") or "").strip()
        if not name or name in seen_pages:
            continue
        seen_pages.add(name)
        pages.append(name)
    out["pages"] = pages

    # Scanner templates
    scanners: list[dict[str, Any]] = []
    for sc in root.findall(".//ScannerContent"):
        scan_type = sc.find("./ScanType")
        adv = sc.find("./AdvancedFilter")
        filters: dict[str, str] = {}
        if adv is not None:
            for node in adv.iter():
                if list(node):
                    continue
                txt = (node.text or "").strip()
                if not txt:
                    continue
                filters[node.tag] = txt

        scanner_name = (sc.get("scannerName") or "").strip()
        display_name = (scan_type.get("displayName") if scan_type is not None else "") or ""
        if not scanner_name:
            scanner_name = display_name or f"Scanner-{sc.get('pageId') or len(scanners)+1}"

        scanners.append(
            {
                "scanner_name": scanner_name,
                "scan_code": (scan_type.get("scanCode") if scan_type is not None else "") or "",
                "display_name": display_name,
                "location_text": (sc.get("locationText") or ""),
                "snapshot": (sc.get("snapshot") or ""),
                "filters": filters,
            }
        )

    out["scanners"] = scanners
    return out


def pick_ibkr_scanner(scanners: list[dict[str, Any]], scanner_name: str | None = None) -> dict[str, Any] | None:
    if not scanners:
        return None
    if scanner_name:
        for s in scanners:
            if str(s.get("scanner_name", "")).strip().lower() == scanner_name.strip().lower():
                return s
    for s in scanners:
        code = str(s.get("scan_code", "")).upper()
        if "OPT_IMP_VOL" in code:
            return s
    return scanners[0]
