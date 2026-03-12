from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime, timezone
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


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".idea",
    ".vscode",
    # Cache / derived artifacts. Must never be part of the integrity manifest,
    # otherwise git-archive based repo snapshots will fail verify_manifest.
    "_repo_cache",
}


# Files that may be generated locally and should never be tracked by the
# integrity manifest (they are re-creatable outputs).
EXCLUDE_FILES = {
    "reports/plan_certification.md",
    "reports/step_certification.md",
}


EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".duckdb",
    ".parquet",
    ".pq",
    ".pkl",
    ".sqlite",
    ".db",
    ".tmp",
    ".log",
    ".zip",  # prevent PATCH_*.zip accidentally entering the manifest
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


def _sha256(path: Path, *, manifest_self_placeholder: bool = False) -> tuple[str, int]:
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


def _utc_build_line() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Build: {ts}"


def _collect_files(repo_root: Path) -> list[str]:
    files: list[str] = []
    for p in repo_root.rglob("*"):
        if p.is_dir():
            continue

        rel = p.relative_to(repo_root).as_posix()

        # Exclude specific generated/derived files.
        if rel in EXCLUDE_FILES:
            continue

        # Exclude any report files that are clearly derived certifications.
        if rel.startswith("reports/") and "certification" in p.name.lower():
            continue

        # Exclude directories by any path segment match
        if any(seg in EXCLUDE_DIRS for seg in p.parts):
            continue

        # Runtime logs are volatile; keep only placeholder file.
        if rel.startswith("logs/") and p.name != ".gitkeep":
            continue

        # Avoid including repo-level patch zips (and other archives / transient artifacts)
        if p.suffix.lower() in EXCLUDE_EXTS and p.name != ".gitkeep":
            continue

        if p.name in {"Thumbs.db", ".DS_Store"}:
            continue

        files.append(rel)

    return sorted(set(files))



def _split_manifest(manifest_text: str) -> tuple[list[str], list[str]]:
    """
    Returns (header_lines_including_hash_header, trailing_lines_after_hash_section).
    Any existing hash lines are discarded.
    """
    lines = manifest_text.splitlines()
    out: list[str] = []
    trail: list[str] = []
    in_hash = False
    for ln in lines:
        if ln.startswith("Build: "):
            out.append(_utc_build_line())
            continue
        if ln.strip() == "Hash SHA256 (file, size):":
            in_hash = True
            out.append(ln)
            continue
        if not in_hash:
            out.append(ln)
            continue
        # in hash section
        if not ln.strip():
            # preserve blank lines immediately after header for readability
            out.append(ln)
            continue
        if LINE_RE.match(ln.strip()):
            # drop existing hash lines
            continue
        # first non-hash, non-empty line ends section -> keep as trailing (future-proof)
        trail.append(ln)
        in_hash = False
    # If trailing was collected, include remaining lines after first trailing marker:
    if trail:
        # include the rest of original lines after the first trailing line
        idx = lines.index(trail[0])
        trail = lines[idx:]
    return out, trail


def rebuild_manifest(manifest_path: Path) -> None:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing MANIFEST: {manifest_path}")

    repo_root = manifest_path.parent.parent
    header, trailing = _split_manifest(manifest_path.read_text(encoding="utf-8", errors="replace"))

    rel_files = _collect_files(repo_root)

    # Build hash lines (placeholder for MANIFEST itself)
    hash_lines: list[str] = []
    for rel in rel_files:
        fp = (repo_root / rel)
        if fp.name == "MANIFEST.txt" and fp.parent.name == ".canonici":
            sha = "0" * 64  # placeholder; filled after first write
            size = len(_read_bytes_normalized(fp))  # stable length
            hash_lines.append(f"{sha} {size:>12d}  {rel}")
            continue
        sha, size = _sha256(fp, manifest_self_placeholder=True)
        hash_lines.append(f"{sha} {size:>12d}  {rel}")

    # Write placeholder manifest
    text = "\n".join(header + hash_lines + trailing).rstrip() + "\n"
    manifest_path.write_text(text, encoding="utf-8", newline="\n")

    # Compute MANIFEST normalized size first, then patch the MANIFEST line size deterministically.
    # This avoids a subtle self-hash mismatch when the size field changes after initial write.
    _tmp_sha, man_size = _sha256(manifest_path, manifest_self_placeholder=True)

    lines = manifest_path.read_text(encoding="utf-8", errors="replace").splitlines()
    size_patched: list[str] = []
    for ln in lines:
        m = LINE_RE.match(ln.strip())
        if m and m.group("path").strip().endswith(".canonici/MANIFEST.txt"):
            size_patched.append(f"{'0'*64} {man_size:>12d}  .canonici/MANIFEST.txt")
        else:
            size_patched.append(ln)
    manifest_path.write_text("\n".join(size_patched).rstrip() + "\n", encoding="utf-8", newline="\n")

    # Now compute MANIFEST self hash using placeholder algorithm (zeros out its own sha field, keeps size field).
    man_sha, _ = _sha256(manifest_path, manifest_self_placeholder=True)

    lines2 = manifest_path.read_text(encoding="utf-8", errors="replace").splitlines()
    final_patched: list[str] = []
    for ln in lines2:
        m = LINE_RE.match(ln.strip())
        if m and m.group("path").strip().endswith(".canonici/MANIFEST.txt"):
            final_patched.append(f"{man_sha} {man_size:>12d}  .canonici/MANIFEST.txt")
        else:
            final_patched.append(ln)

    manifest_path.write_text("\n".join(final_patched).rstrip() + "\n", encoding="utf-8", newline="\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="rebuild_manifest")
    p.add_argument("--manifest", default=".canonici/MANIFEST.txt")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rebuild_manifest(Path(args.manifest))
    print("MANIFEST rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
