from __future__ import annotations

import argparse
import sys
from pathlib import Path


GITATTRIBUTES_CONTENT = (
    "# QuantOpzioni.AI\n"
    "#\n"
    "# We do NOT want Git to normalize line endings across environments.\n"
    "# The repository uses an integrity MANIFEST that is byte-sensitive.\n"
    "# Keep file contents as-is and let the developer's environment decide.\n"
    "*\t-text\n"
)


def ensure_gitattributes(repo_root: Path) -> None:
    p = repo_root / ".gitattributes"
    if p.exists():
        cur = p.read_text(encoding="utf-8", errors="replace")
        if cur.replace("\r\n", "\n") == GITATTRIBUTES_CONTENT:
            return
    p.write_text(GITATTRIBUTES_CONTENT, encoding="utf-8", newline="\n")


def ensure_gitignore_whitelist(repo_root: Path) -> None:
    p = repo_root / ".gitignore"
    if not p.exists():
        return
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if "!.gitattributes" in lines:
        return
    out: list[str] = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if ln.strip() == "!.step_index.json" and not inserted:
            out.append("!.gitattributes")
            inserted = True
    if not inserted:
        out2: list[str] = []
        for ln in out:
            out2.append(ln)
            if ln.strip() == ".*" and not inserted:
                out2.append("!.gitattributes")
                inserted = True
        out = out2
    p.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fix_portable_snapshot")
    ap.add_argument("--manifest", default=".canonici/MANIFEST.txt")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    ensure_gitattributes(repo_root)
    ensure_gitignore_whitelist(repo_root)

    from tools.rebuild_manifest import rebuild_manifest

    rebuild_manifest(repo_root / args.manifest)
    print("OK portable snapshot: .gitattributes ensured; MANIFEST rebuilt")

    # Verify immediately
    from tools.verify_manifest import verify_manifest

    ok = verify_manifest(repo_root / args.manifest)
    if not ok:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())