from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Iterable

LINE_RE = re.compile(r"^(?P<sha>[0-9a-f]{64})\s+(?P<size>\d+)\s+(?P<path>.+)$")

TEXT_EXTS = {
    ".md", ".txt", ".py", ".toml", ".json", ".ps1", ".diff", ".gitignore", ".bat",
    ".yml", ".yaml", ".csv", ".jsonl", ".sha256",
    ".lock", ".ini", ".cfg", ".env",
}

TEXT_FILENAMES = {
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "requirements.lock",
}


def _is_text_path(p: Path) -> bool:
    if p.name == ".gitkeep":
        return True
    if p.name in TEXT_FILENAMES:
        return True
    return p.suffix.lower() in TEXT_EXTS


def _read_bytes_normalized(path: Path) -> bytes:
    b = path.read_bytes()
    if _is_text_path(path):
        b = b.replace(b"\r\n", b"\n")
    return b


def _sha256_normalized(path: Path, *, manifest_self_placeholder: bool = False) -> tuple[str, int]:
    b = _read_bytes_normalized(path)
    if manifest_self_placeholder and path.name == "MANIFEST.txt":
        txt = b.decode("utf-8", errors="replace").splitlines(True)
        out_lines: list[str] = []
        for line in txt:
            stripped = line.strip()
            m = LINE_RE.match(stripped)
            if m and m.group("path").strip().endswith("MANIFEST.txt"):
                out_lines.append(("0" * 64) + stripped[64:] + ("\n" if not line.endswith("\n") else ""))
            else:
                out_lines.append(line)
        b = "".join(out_lines).encode("utf-8")
    return hashlib.sha256(b).hexdigest(), len(_read_bytes_normalized(path))


def _iter_manifest_hash_lines(manifest_text: str) -> Iterable[tuple[str, int, str]]:
    lines = manifest_text.splitlines()
    try:
        start = lines.index("Hash SHA256 (file, size):")
    except ValueError as e:
        raise ValueError("MANIFEST is missing 'Hash SHA256 (file, size):' header") from e

    started = False
    for ln in lines[start + 1 :]:
        if not ln.strip():
            if started:
                continue
            continue
        m = LINE_RE.match(ln.strip())
        if not m:
            break
        started = True
        yield m.group("sha"), int(m.group("size")), m.group("path").strip()


def verify_manifest(manifest_path: Path) -> tuple[bool, list[str]]:
    if not manifest_path.exists():
        return False, [f"missing manifest: {manifest_path}"]

    repo_root = manifest_path.parent.parent
    txt = manifest_path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    seen: set[str] = set()

    for sha, size, rel in _iter_manifest_hash_lines(txt):
        rel_norm = rel.replace("\\", "/")
        if rel_norm in seen:
            errors.append(f"duplicate entry: {rel_norm}")
            continue
        seen.add(rel_norm)

        fp = (repo_root / rel_norm).resolve()
        if not fp.exists():
            errors.append(f"missing file: {rel_norm}")
            continue

        got_sha, got_size = _sha256_normalized(fp, manifest_self_placeholder=True)
        if got_size != size:
            errors.append(f"size mismatch: {rel_norm} expected={size} got={got_size}")
        if got_sha != sha:
            errors.append(f"sha mismatch: {rel_norm} expected={sha[:12]}… got={got_sha[:12]}…")

    return len(errors) == 0, errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="verify_manifest")
    p.add_argument("--manifest", default=".canonici/MANIFEST.txt")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ok, errors = verify_manifest(Path(args.manifest))
    if ok:
        print("VERIFY_MANIFEST OK")
        return 0

    print("VERIFY_MANIFEST FAIL")
    for e in errors[:200]:
        print(f"- {e}")
    if len(errors) > 200:
        print(f"... ({len(errors)-200} more)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
