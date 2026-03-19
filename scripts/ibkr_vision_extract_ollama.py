from __future__ import annotations

import argparse
import base64
import glob
import json
import urllib.request
from pathlib import Path
from typing import Any


def _extract_json(text: str) -> dict[str, Any]:
    s = text or ""
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(s[i : j + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return {"raw": s}


def _chat_ollama(*, host: str, model: str, image_path: Path, timeout_sec: int) -> dict[str, Any]:
    prompt = (
        "Sei un parser finanziario. Estrai SOLO JSON valido, senza testo extra. "
        "Schema: {tab:string, rows:[{symbol:string,last:number|null,bid:number|null,ask:number|null,"
        "vs_pct:number|null,vi_pct:number|null,strategy:string|null,group:string|null,notes:string|null}]}. "
        "Usa null se il valore non è leggibile. Simboli sempre UPPERCASE."
    )
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    payload_chat = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
    }
    data_chat = json.dumps(payload_chat).encode("utf-8")
    req_chat = urllib.request.Request(
        url=f"{host.rstrip('/')}/api/chat",
        data=data_chat,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req_chat, timeout=timeout_sec) as resp:
            out = json.loads(resp.read().decode("utf-8", errors="replace"))
        msg = ((out or {}).get("message") or {}).get("content") or ""
        parsed = _extract_json(msg)
        return {"raw_response": msg, "parsed": parsed, "endpoint": "/api/chat"}
    except Exception:
        pass

    payload_gen = {
        "model": model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
    }
    data_gen = json.dumps(payload_gen).encode("utf-8")
    req_gen = urllib.request.Request(
        url=f"{host.rstrip('/')}/api/generate",
        data=data_gen,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_gen, timeout=timeout_sec) as resp:
        out = json.loads(resp.read().decode("utf-8", errors="replace"))
    msg = (out or {}).get("response") or ""
    parsed = _extract_json(msg)
    return {"raw_response": msg, "parsed": parsed, "endpoint": "/api/generate"}


def _save_progress(path: Path, model: str, host: str, images: list[Path], results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "host": host,
        "images": [p.as_posix() for p in images],
        "results": results,
        "merged_rows": [],
        "merged_count": 0,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    paths: list[Path] = []
    for pat in args.images:
        for p in glob.glob(pat):
            pp = Path(p)
            if pp.is_file():
                paths.append(pp)
    paths = sorted(set(paths))

    out_path = Path(args.output)
    results: list[dict[str, Any]] = []

    for p in paths:
        try:
            r = _chat_ollama(host=args.host, model=args.model, image_path=p, timeout_sec=args.timeout_sec)
            results.append({"file": p.as_posix(), "ok": True, **r})
        except Exception as exc:
            results.append({"file": p.as_posix(), "ok": False, "error": str(exc)})
        _save_progress(out_path, args.model, args.host, paths, results)

    merged_rows: list[dict[str, Any]] = []
    for x in results:
        if not x.get("ok"):
            continue
        parsed = x.get("parsed")
        if isinstance(parsed, dict):
            rows = parsed.get("rows")
            tab = parsed.get("tab")
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict):
                        rr = dict(r)
                        if tab and "tab" not in rr:
                            rr["tab"] = tab
                        merged_rows.append(rr)

    out = {
        "model": args.model,
        "host": args.host,
        "images": [p.as_posix() for p in paths],
        "results": results,
        "merged_rows": merged_rows,
        "merged_count": len(merged_rows),
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": out_path.as_posix(), "images": len(paths), "merged_count": len(merged_rows)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ibkr_vision_extract_ollama")
    p.add_argument("--host", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="llava:7b")
    p.add_argument("--images", nargs="+", default=["data/ibkr_screens/*_crop_s.jpg"])
    p.add_argument("--output", default="data/ibkr_screens/ollama_vision_extraction.json")
    p.add_argument("--timeout-sec", type=int, default=75)
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    info = run(a)
    if a.format == "json":
        print(json.dumps(info, ensure_ascii=False))
    else:
        print(f"IBKR_VISION_EXTRACT images={info['images']} merged_rows={info['merged_count']} output={info['output']}")
