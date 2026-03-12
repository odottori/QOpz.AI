from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

# Force conservative CPU runtime (avoid PIR/oneDNN path that crashes on some Windows builds)
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from paddleocr import PaddleOCR

TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")


def _norm_line(s: str) -> str:
    return " ".join((s or "").replace("\t", " ").split())


def _guess_tab_from_name(name: str) -> str:
    b = name.lower()
    if b.startswith("1"):
        return "titoli"
    if b.startswith("2"):
        return "opzioni"
    if b.startswith("4"):
        return "ciclo_economico"
    if b.startswith("5"):
        return "indici"
    if b.startswith("3"):
        return "watchlist"
    return "unknown"


def _make_ocr() -> PaddleOCR:
    candidates = [
        {"lang": "en", "use_textline_orientation": False, "enable_mkldnn": False, "cpu_threads": 1},
        {"lang": "en", "use_textline_orientation": False},
        {"lang": "en", "use_angle_cls": False},
    ]
    last_err: Exception | None = None
    for kwargs in candidates:
        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"PaddleOCR init failed: {last_err}")


def _predict_lines(ocr: PaddleOCR, img_path: str) -> list[str]:
    # New API
    if hasattr(ocr, "predict"):
        out: list[str] = []
        result = ocr.predict(img_path)
        for item in result or []:
            rec = item if isinstance(item, dict) else {}
            texts = rec.get("rec_texts") or []
            if isinstance(texts, list):
                out.extend([_norm_line(str(t)) for t in texts if str(t).strip()])
        return [x for x in out if x]

    # Legacy API
    result = ocr.ocr(img_path, cls=False)
    out: list[str] = []
    for block in result or []:
        for item in block or []:
            try:
                txt = str(item[1][0])
            except Exception:
                continue
            line = _norm_line(txt)
            if line:
                out.append(line)
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    image_dir = Path(args.image_dir)
    images = sorted([p for p in image_dir.glob(args.pattern) if p.is_file()])

    if not images:
        raise RuntimeError(f"No images found with pattern '{args.pattern}' in {image_dir.as_posix()}")

    ocr = _make_ocr()

    out_rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    for img in images:
        lines = _predict_lines(ocr, str(img))
        symbols: set[str] = set()

        for line in lines:
            for m in TICKER_RE.findall(line):
                if m in {"USD", "EUR", "GBP", "APR", "MAR", "MAG", "GIU", "LUG", "DIC"}:
                    continue
                symbols.add(m)
                out_rows.append(
                    {
                        "file": img.name,
                        "tab": _guess_tab_from_name(img.name),
                        "symbol": m,
                        "raw_line": line,
                    }
                )

        files.append(
            {
                "file": img.name,
                "tab": _guess_tab_from_name(img.name),
                "lines_count": len(lines),
                "symbols_detected": sorted(symbols),
            }
        )

    payload = {
        "source": "paddleocr",
        "image_dir": image_dir.as_posix(),
        "pattern": args.pattern,
        "files": files,
        "rows": out_rows,
        "rows_count": len(out_rows),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": out.as_posix(), "images": len(images), "rows_count": len(out_rows)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ibkr_ocr_paddle_extract")
    p.add_argument("--image-dir", default="data/ibkr_screens")
    p.add_argument("--pattern", default="*_crop_s.jpg")
    p.add_argument("--output", default="data/ibkr_screens/paddle_ocr_extraction.json")
    p.add_argument("--format", choices=["line", "json"], default="line")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    info = run(a)
    if a.format == "json":
        print(json.dumps(info, ensure_ascii=False))
    else:
        print(f"PADDLE_OCR_EXTRACT images={info['images']} rows={info['rows_count']} output={info['output']}")
