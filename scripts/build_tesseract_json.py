import json, re, pathlib

root = pathlib.Path("data/ibkr_screens/ocr_txt")
rows = []

for p in sorted(root.glob("*.txt")):
    n = p.stem
    if n.startswith("1"):
        tab = "titoli"
    elif n.startswith("2"):
        tab = "opzioni"
    elif n.startswith("4"):
        tab = "ciclo_economico"
    elif n.startswith("5"):
        tab = "indici"
    else:
        tab = "watchlist"

    txt = p.read_text(encoding="utf-8", errors="ignore")
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        for s in re.findall(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b", line):
            if s in {"USD","EUR","GBP","APR","MAR","MAG","GIU","LUG","DIC"}:
                continue
            rows.append({"file": p.name, "tab": tab, "symbol": s, "raw_line": line})

out = {"source": "tesseract", "rows_count": len(rows), "rows": rows}
out_path = pathlib.Path("data/ibkr_screens/tesseract_extraction.json")
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"WROTE {out_path} rows={len(rows)}")
