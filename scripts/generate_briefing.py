#!/usr/bin/env python3
"""
generate_briefing.py — Briefing audio mattutino QOpz.AI

Genera un bollettino audio MP3 con la situazione operativa del giorno:
  - Regime corrente
  - Equity e drawdown
  - Exit urgenti
  - Opportunità top
  - Kelly status

Richiede: edge-tts (pip install edge-tts), httpx, tomllib (Python 3.11+)

Uso:
  python scripts/generate_briefing.py                  # genera + invia Telegram
  python scripts/generate_briefing.py --no-telegram    # solo file MP3
  python scripts/generate_briefing.py --text-only      # stampa testo senza audio
  python scripts/generate_briefing.py --api http://localhost:8765  # API custom
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Config ────────────────────────────────────────────────────────────────────

def _load_telegram_cfg() -> dict:
    cfg_path = ROOT / "config" / "telegram.toml"
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "rb") as f:
        return tomllib.load(f)


def _audio_dir() -> Path:
    cfg = _load_telegram_cfg()
    d = ROOT / cfg.get("briefing", {}).get("audio_dir", "data/audio")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tts_voice() -> str:
    cfg = _load_telegram_cfg()
    return cfg.get("briefing", {}).get("voice", "it-IT-ElsaNeural")


# ── API calls ─────────────────────────────────────────────────────────────────

def _get(api_base: str, path: str) -> dict:
    import httpx
    try:
        r = httpx.get(f"{api_base}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[WARN] {path}: {e}", file=sys.stderr)
        return {}


def _fetch_data(api_base: str) -> dict:
    return {
        "regime":   _get(api_base, "/opz/regime/current"),
        "summary":  _get(api_base, "/opz/paper/summary?profile=paper&window_days=60"),
        "status":   _get(api_base, "/opz/system/status"),
        "tier":     _get(api_base, "/opz/tier?profile=paper"),
        "exits":    _get(api_base, "/opz/opportunity/exit_candidates?profile=paper"),
    }


# ── Testo briefing ────────────────────────────────────────────────────────────

def _compose_text(data: dict) -> str:
    now = datetime.now(tz=timezone.utc)
    giorno = now.strftime("%A %d %B %Y").capitalize()
    ora    = now.strftime("%H:%M UTC")

    regime_data = data.get("regime", {})
    summary     = data.get("summary", {})
    status      = data.get("status", {})
    tier        = data.get("tier", {})
    exits_data  = data.get("exits", {})

    regime       = regime_data.get("regime", "SCONOSCIUTO")
    n_recenti    = regime_data.get("n_recent", 0)
    trades       = summary.get("trades", 0)
    sharpe       = summary.get("sharpe_annualized")
    win_rate     = summary.get("win_rate")
    max_dd       = summary.get("max_drawdown")
    profit_f     = summary.get("profit_factor")
    kelly_on     = status.get("kelly_enabled", False)
    data_mode    = status.get("data_mode", "SYNTHETIC_SURFACE_CALIBRATED")
    ks_active    = status.get("kill_switch_active", False)
    capital_tier = tier.get("capital_tier", "MICRO")
    active_mode  = tier.get("active_mode", "MICRO")
    n_closed     = tier.get("data_gate", {}).get("n_closed", 0)

    exits    = exits_data.get("candidates", [])
    urgenti  = [e for e in exits if e.get("exit_score", 0) >= 5]

    lines: list[str] = []

    # ── Intro ─────────────────────────────────────────────────────────────────
    lines.append(f"Buongiorno. Briefing operativo di {giorno}, ore {ora}.")
    lines.append("")

    # ── Kill switch ───────────────────────────────────────────────────────────
    if ks_active:
        lines.append("ATTENZIONE. Il kill switch è attivo. Tutti gli ordini sono bloccati. "
                     "Verifica la situazione prima di procedere.")
        lines.append("")

    # ── Regime ────────────────────────────────────────────────────────────────
    regime_desc = {
        "NORMAL":  "Il regime è NORMALE. Il mercato è in condizioni regolari, "
                   "puoi operare con sizing pieno.",
        "CAUTION": "Il regime è in ATTENZIONE. La volatilità è elevata. "
                   "Usa sizing ridotto al 50 percento e preferisci spread stretti.",
        "SHOCK":   "ATTENZIONE: regime di SHOCK. Non aprire nuove posizioni. "
                   "Monitora le uscite e attendi il ritorno alla normalità.",
    }.get(regime, f"Regime: {regime}. Procedi con cautela.")

    lines.append(regime_desc)
    if n_recenti > 0:
        lines.append(f"Campione regime basato su {n_recenti} osservazioni recenti.")
    lines.append("")

    # ── Equity ────────────────────────────────────────────────────────────────
    lines.append("SITUAZIONE PORTAFOGLIO.")
    lines.append(f"Trade completati: {trades}.")
    if win_rate is not None:
        lines.append(f"Win rate: {win_rate * 100:.1f} percento.")
    if sharpe is not None:
        lines.append(f"Sharpe annualizzato: {sharpe:.2f}.")
    if max_dd is not None:
        dd_pct = max_dd * 100
        if dd_pct > 15:
            lines.append(f"Drawdown massimo: {dd_pct:.1f} percento — vicino al limite del 20 percento. Attenzione.")
        elif dd_pct > 8:
            lines.append(f"Drawdown massimo: {dd_pct:.1f} percento — nella zona di cautela.")
        else:
            lines.append(f"Drawdown massimo: {dd_pct:.1f} percento — sotto controllo.")
    if profit_f is not None:
        lines.append(f"Profit factor: {profit_f:.2f}.")
    lines.append("")

    # ── Exit urgenti ──────────────────────────────────────────────────────────
    if urgenti:
        lines.append(f"ATTENZIONE: {len(urgenti)} uscita urgente rilevata." if len(urgenti) == 1
                     else f"ATTENZIONE: {len(urgenti)} uscite urgenti rilevate.")
        for e in urgenti[:3]:
            sym = e.get("symbol", "?")
            score = e.get("exit_score", 0)
            reason = e.get("exit_reason") or e.get("reason", "")
            lines.append(f"  {sym}: score {score:.1f} — {reason}.")
        lines.append("Gestisci queste uscite prima di aprire nuove posizioni.")
    elif exits:
        lines.append(f"Nessuna uscita urgente. {len(exits)} posizioni monitorate regolarmente.")
    else:
        lines.append("Nessuna posizione aperta in monitoraggio.")
    lines.append("")

    # ── Tier / Kelly ──────────────────────────────────────────────────────────
    lines.append(f"Tier operativo: {active_mode}. Tier capitale: {capital_tier}.")
    if kelly_on:
        lines.append("Kelly sizing: ABILITATO. Usa la frazione suggerita dal sistema.")
    else:
        if data_mode != "VENDOR_REAL_CHAIN":
            lines.append("Kelly sizing: disabilitato. I dati sono sintetici, non reali.")
        elif n_closed < 50:
            lines.append(f"Kelly sizing: disabilitato. Servono {50 - n_closed} trade chiusi aggiuntivi "
                         f"per raggiungere il minimo statistico.")
        else:
            lines.append("Kelly sizing: disabilitato. Verifica le condizioni nel pannello sistema.")
    lines.append("")

    # ── Chiusura ──────────────────────────────────────────────────────────────
    if regime == "SHOCK" or ks_active:
        lines.append("Giornata operativa sospesa. Monitora la situazione e attendi segnali di stabilizzazione.")
    elif regime == "CAUTION":
        lines.append("Procedi con prudenza. Esegui lo scan e seleziona solo i candidati con score superiore a 0.7.")
    else:
        lines.append("Puoi procedere con la routine operativa. Avvia lo scan, seleziona il candidato migliore, "
                     "verifica la preview e conferma l'ordine.")

    lines.append("Buona giornata operativa.")

    return "\n".join(lines)


# ── TTS ───────────────────────────────────────────────────────────────────────

async def _generate_mp3(text: str, out_path: Path, voice: str) -> None:
    try:
        import edge_tts
    except ImportError:
        print("edge-tts non installato: pip install edge-tts", file=sys.stderr)
        raise

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
    print(f"[OK] Audio salvato: {out_path}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def _send_telegram(mp3_path: Path, caption: str) -> None:
    import httpx

    cfg = _load_telegram_cfg()
    tg = cfg.get("telegram", {})
    token   = tg.get("bot_token", os.environ.get("TG_BOT_TOKEN", ""))
    chat_id = tg.get("chat_id", os.environ.get("TG_CHAT_ID", ""))

    if not token or not chat_id:
        print("[WARN] Token o chat_id Telegram mancanti — skip invio.", file=sys.stderr)
        return

    base_url = f"https://api.telegram.org/bot{token}"

    # Invia testo
    try:
        httpx.post(f"{base_url}/sendMessage", json={
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
        }, timeout=15)
    except Exception as e:
        print(f"[WARN] sendMessage fallito: {e}", file=sys.stderr)

    # Invia audio MP3
    if mp3_path.exists():
        with open(mp3_path, "rb") as f:
            try:
                httpx.post(f"{base_url}/sendAudio", data={
                    "chat_id": str(chat_id),
                    "title": "QOpz Briefing",
                    "performer": "QOpz.AI",
                }, files={"audio": (mp3_path.name, f, "audio/mpeg")}, timeout=60)
                print(f"[OK] Audio inviato su Telegram (chat_id={chat_id})")
            except Exception as e:
                print(f"[WARN] sendAudio fallito: {e}", file=sys.stderr)


def _build_telegram_caption(text: str) -> str:
    """Versione testuale breve per il messaggio Telegram (max 4096 chars)."""
    lines = [l for l in text.split("\n") if l.strip()]
    # Prendi le prime righe fino a ~800 chars
    out = []
    total = 0
    for l in lines:
        if total + len(l) > 800:
            out.append("...")
            break
        out.append(l)
        total += len(l)
    return "\n".join(out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Genera briefing audio QOpz.AI")
    parser.add_argument("--api",          default="http://localhost:8765", help="Base URL API")
    parser.add_argument("--no-telegram",  action="store_true", help="Non inviare su Telegram")
    parser.add_argument("--text-only",    action="store_true", help="Solo testo, nessun MP3")
    parser.add_argument("--out",          default=None,        help="Path output MP3 (default: auto)")
    args = parser.parse_args()

    print(f"[INFO] Connessione API: {args.api}")
    data = _fetch_data(args.api)
    text = _compose_text(data)

    if args.text_only:
        print("\n" + "="*60)
        print(text)
        print("="*60)
        return

    # Path output
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    if args.out:
        mp3_path = Path(args.out)
    else:
        mp3_path = _audio_dir() / f"briefing_{ts}.mp3"

    voice = _tts_voice()
    print(f"[INFO] Generazione audio — voce: {voice}")
    asyncio.run(_generate_mp3(text, mp3_path, voice))

    # Symlink/copia come "latest"
    latest = _audio_dir() / "briefing_latest.mp3"
    if latest.exists():
        latest.unlink()
    try:
        latest.hardlink_to(mp3_path)
    except Exception:
        import shutil
        shutil.copy2(mp3_path, latest)

    if not args.no_telegram:
        caption = _build_telegram_caption(text)
        _send_telegram(mp3_path, caption)

    print(f"[DONE] Briefing completato: {mp3_path}")


if __name__ == "__main__":
    main()
