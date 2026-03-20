#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx


ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "telegram.toml"


@dataclass(frozen=True)
class BotConfig:
    token: str
    allowed_chat_ids: set[str]
    api_base: str
    poll_timeout_sec: int
    poll_sleep_sec: float
    offset_path: Path


def _load_cfg_file() -> dict[str, Any]:
    if not CFG_PATH.exists():
        return {}
    with CFG_PATH.open("rb") as f:
        raw = tomllib.load(f)
    return raw if isinstance(raw, dict) else {}


def _env_or_cfg(env_name: str, cfg_value: Any, default: str = "") -> str:
    val = os.environ.get(env_name)
    if val is not None and str(val).strip():
        return str(val).strip()
    if cfg_value is None:
        return default
    txt = str(cfg_value).strip()
    return txt if txt else default


def _parse_chat_ids(value: str) -> set[str]:
    out: set[str] = set()
    for part in str(value).split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out


def load_bot_config() -> BotConfig:
    cfg = _load_cfg_file()
    tg = cfg.get("telegram", {}) if isinstance(cfg.get("telegram"), dict) else {}

    token = _env_or_cfg("TG_BOT_TOKEN", tg.get("bot_token"))
    if not token:
        raise RuntimeError("Missing TG_BOT_TOKEN and config/telegram.toml telegram.bot_token")

    chat_cfg = _env_or_cfg("TG_CHAT_ID", tg.get("chat_id"))
    chat_ids_cfg = _env_or_cfg("TG_CHAT_IDS", "")
    allowed = _parse_chat_ids(",".join([chat_cfg, chat_ids_cfg]))
    if not allowed:
        raise RuntimeError("Missing allowed chat id (TG_CHAT_ID/TG_CHAT_IDS or config telegram.chat_id)")

    api_base = _env_or_cfg("TG_COMMAND_API_BASE", "http://api:8765", default="http://api:8765").rstrip("/")
    poll_timeout = int(_env_or_cfg("TG_POLL_TIMEOUT_SEC", "30", default="30"))
    poll_sleep = float(_env_or_cfg("TG_POLL_SLEEP_SEC", "1.0", default="1.0"))
    offset_path = Path(_env_or_cfg("TG_OFFSET_PATH", str(ROOT / "data" / "telegram" / "offset.txt")))
    offset_path.parent.mkdir(parents=True, exist_ok=True)

    return BotConfig(
        token=token,
        allowed_chat_ids=allowed,
        api_base=api_base,
        poll_timeout_sec=max(1, min(poll_timeout, 60)),
        poll_sleep_sec=max(0.1, min(poll_sleep, 10.0)),
        offset_path=offset_path,
    )


def _load_offset(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _save_offset(path: Path, offset: int) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(int(offset)), encoding="utf-8")
    os.replace(tmp, path)


def _normalize_command(text: str) -> str:
    t = (text or "").strip().upper()
    if not t:
        return ""
    while t.startswith("/") or t.startswith("\\"):
        t = t[1:]
    t = t.replace("_", " ").replace("-", " ")
    t = " ".join(part for part in t.split() if part)
    aliases = {
        "STATUS": "STATUS",
        "HELP": "HELP",
        "H": "HELP",
        "OBSERVER ON": "OBSERVER ON",
        "OBSERVER OFF": "OBSERVER OFF",
        "OBSERVERON": "OBSERVER ON",
        "OBSERVEROFF": "OBSERVER OFF",
        "OBSERVER YES": "OBSERVER ON",
        "OBSERVER NO": "OBSERVER OFF",
    }
    return aliases.get(t, t)


def _send_message(client: httpx.Client, token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = client.post(url, data={"chat_id": chat_id, "text": text}, timeout=15.0)
    resp.raise_for_status()


def _api_json(client: httpx.Client, api_base: str, path: str, *, method: str = "GET", payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    url = f"{api_base}{path}"
    if method == "POST":
        resp = client.post(url, json=(payload or {}), timeout=12.0)
    else:
        resp = client.get(url, timeout=12.0)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _build_help_text() -> str:
    return (
        "HELP - COMANDI DISPONIBILI\n\n"
        "/status\n"
        "- stato OBSERVER, IBWR/IBG, API, regime, readiness\n\n"
        "/observer on\n"
        "- richiede IBWR connesso\n"
        "- se IBWR non connesso resta OFF\n\n"
        "/observer off\n"
        "- forza kill switch ON\n"
        "- blocca operativita ordini\n\n"
        "/help\n"
        "- mostra questo elenco\n\n"
        "Alias supportati: STATUS, HELP, OBSERVER ON/OFF, \\status"
    )


def _build_status_text(status: dict[str, Any]) -> str:
    ks = bool(status.get("kill_switch_active"))
    ibkr_connected = bool(status.get("ibkr_connected"))
    ibkr_port = status.get("ibkr_port")
    regime = str(status.get("regime") or "UNKNOWN")
    data_mode = str(status.get("data_mode") or "UNKNOWN")
    hr = status.get("history_readiness") if isinstance(status.get("history_readiness"), dict) else {}

    observer_state = "OFF" if ks else "ON"
    ibwr_state = "ON" if ibkr_connected else "OFF"
    h_score = hr.get("score_pct")
    h_days = f"{hr.get('days_observed', 0)}/{hr.get('target_days', 0)}"
    h_events = f"{hr.get('events_observed', 0)}/{hr.get('target_events', 0)}"
    h_eta = hr.get("eta_days")
    eta_label = "n/d" if h_eta is None else ("oggi" if int(h_eta) == 0 else f"{int(h_eta)}g")

    return (
        "STATUS\n"
        f"OBSERVER: {observer_state} (KS={'ON' if ks else 'OFF'})\n"
        f"IBWR/IBG: {ibwr_state}"
        f"{f' port {ibkr_port}' if ibkr_connected and ibkr_port is not None else ''}\n"
        f"REGIME: {regime}\n"
        f"DATA_MODE: {data_mode}\n"
        f"READINESS: {h_score if h_score is not None else 'n/d'}% | days {h_days} | events {h_events} | ETA {eta_label}"
    )


def _handle_command(client: httpx.Client, cfg: BotConfig, chat_id: str, cmd: str) -> None:
    if cmd == "HELP":
        _send_message(client, cfg.token, chat_id, _build_help_text())
        return

    if cmd == "STATUS":
        try:
            status = _api_json(client, cfg.api_base, "/opz/system/status")
            text = _build_status_text(status)
        except Exception as exc:
            text = f"STATUS ERROR: {type(exc).__name__}: {exc}"
        _send_message(client, cfg.token, chat_id, text)
        return

    if cmd in {"OBSERVER ON", "OBSERVER OFF"}:
        action = "on" if cmd.endswith("ON") else "off"
        try:
            out = _api_json(
                client,
                cfg.api_base,
                "/opz/execution/observer",
                method="POST",
                payload={"action": action, "notify_telegram": False, "source": "telegram_bot"},
            )
            state = out.get("observer_state", "OFF")
            reason = out.get("reason", "UNKNOWN")
            requested = "ON" if action == "on" else "OFF"
            applied = str(out.get("applied_action", "unknown")).upper()
            if state != requested:
                text = (
                    f"OBSERVER {requested} RICHIESTO MA NON ATTIVO\n"
                    f"state={state}\n"
                    f"reason={reason}\n"
                    f"applied={applied}"
                )
            else:
                text = (
                    f"OBSERVER {state} ATTIVO\n"
                    f"reason={reason}\n"
                    f"applied={applied}"
                )
            _send_message(client, cfg.token, chat_id, text)
        except Exception as exc:
            _send_message(client, cfg.token, chat_id, f"OBSERVER ERROR: {type(exc).__name__}: {exc}")
        return

    _send_message(client, cfg.token, chat_id, "Comando non riconosciuto. Scrivi /help.")


def run_loop(cfg: BotConfig, once: bool = False) -> int:
    offset = _load_offset(cfg.offset_path)
    updates_url = f"https://api.telegram.org/bot{cfg.token}/getUpdates"

    with httpx.Client() as client:
        while True:
            try:
                resp = client.get(
                    updates_url,
                    params={"offset": offset, "timeout": cfg.poll_timeout_sec},
                    timeout=cfg.poll_timeout_sec + 10,
                )
                resp.raise_for_status()
                payload = resp.json()
                results = payload.get("result", []) if isinstance(payload, dict) else []
            except Exception as exc:
                print(f"[WARN] getUpdates failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                if once:
                    return 2
                time.sleep(cfg.poll_sleep_sec)
                continue

            max_seen = offset
            for upd in results:
                if not isinstance(upd, dict):
                    continue
                upd_id = int(upd.get("update_id", 0))
                max_seen = max(max_seen, upd_id + 1)

                msg = upd.get("message")
                if not isinstance(msg, dict):
                    continue
                frm = msg.get("from")
                if isinstance(frm, dict) and bool(frm.get("is_bot")):
                    continue
                chat = msg.get("chat")
                if not isinstance(chat, dict):
                    continue
                chat_id = str(chat.get("id", "")).strip()
                if chat_id not in cfg.allowed_chat_ids:
                    continue

                text = str(msg.get("text") or "")
                cmd = _normalize_command(text)
                if not cmd:
                    continue
                _handle_command(client, cfg, chat_id, cmd)

            if max_seen != offset:
                offset = max_seen
                _save_offset(cfg.offset_path, offset)

            if once:
                return 0
            time.sleep(cfg.poll_sleep_sec)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="telegram_command_bot")
    p.add_argument("--once", action="store_true", help="Process one polling cycle then exit")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    cfg = load_bot_config()
    return run_loop(cfg, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
