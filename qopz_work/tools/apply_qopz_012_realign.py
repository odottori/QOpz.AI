from pathlib import Path


def patch_vite_wrapper(base: Path) -> bool:
    candidates = [
        base / "ui" / "node_modules" / ".bin" / "vite",
        base.parent / "ui" / "node_modules" / ".bin" / "vite",
    ]
    changed = False
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        fixed = text.replace("../dist/node/cli.js", "../vite/dist/node/cli.js")
        if fixed != text:
            p.write_text(fixed, encoding="utf-8")
            print(f"[OK] patched {p}")
            changed = True
    return changed


if __name__ == "__main__":
    here = Path(__file__).resolve()
    app_root = here.parents[1]
    if not patch_vite_wrapper(app_root):
        print("[INFO] no broken vite wrapper found")
