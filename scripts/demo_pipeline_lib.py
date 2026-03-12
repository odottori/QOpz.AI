from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "demo_pipeline"
DEFAULT_DB = DATA_ROOT / "index.duckdb"
DEFAULT_RAW_DIR = DATA_ROOT / "raw"
DEFAULT_EXTRACTED_DIR = DATA_ROOT / "extracted"
DEFAULT_DATASET_DIR = DATA_ROOT / "datasets"
DEFAULT_LOG_DIR = DATA_ROOT / "logs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    line = json.dumps(payload, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def duckdb_available() -> bool:
    try:
        importlib.import_module("duckdb")
        return True
    except ModuleNotFoundError:
        return False


def _duckdb_module() -> Any:
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "duckdb module is required for demo pipeline (duckdb-only mode). Install with: py -m pip install duckdb"
        ) from exc


def connect_db(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    duckdb = _duckdb_module()
    return duckdb.connect(str(path))


def fetchall_dicts(conn: Any, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params or [])
    rows = cur.fetchall()
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, row)) for row in rows]


def fetchone_dict(conn: Any, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> dict[str, Any] | None:
    cur = conn.execute(sql, params or [])
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in (cur.description or [])]
    return dict(zip(cols, row))


def init_db(conn: Any) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS captures_id_seq")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS extractions_id_seq")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS captures (
            id BIGINT PRIMARY KEY DEFAULT nextval('captures_id_seq'),
            captured_ts_utc VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            page_type VARCHAR NOT NULL,
            fingerprint_sha256 VARCHAR NOT NULL,
            raw_path VARCHAR NOT NULL,
            payload_format VARCHAR NOT NULL,
            payload_bytes BIGINT NOT NULL,
            status VARCHAR NOT NULL,
            UNIQUE(source, symbol, page_type, fingerprint_sha256)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extractions (
            id BIGINT PRIMARY KEY DEFAULT nextval('extractions_id_seq'),
            capture_id BIGINT NOT NULL,
            extracted_ts_utc VARCHAR NOT NULL,
            model VARCHAR NOT NULL,
            prompt_version VARCHAR NOT NULL,
            backend VARCHAR NOT NULL,
            attempts INTEGER NOT NULL,
            status VARCHAR NOT NULL,
            output_path VARCHAR,
            error_text VARCHAR,
            UNIQUE(capture_id, model, prompt_version)
        )
        """
    )
