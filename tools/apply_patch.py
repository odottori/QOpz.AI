from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
import subprocess


def _ensure_repo_root() -> None:
    required = ["validator.py", ".qoaistate.json"]
    missing = [p for p in required if not Path(p).exists()]
    if missing:
        raise SystemExit(f"ERROR: not repo root (missing: {', '.join(missing)})")


def apply_zip(patch_zip: Path) -> None:
    if not patch_zip.exists():
        raise SystemExit(f"ERROR: patch zip not found: {patch_zip}")
    with zipfile.ZipFile(patch_zip, "r") as z:
        z.extractall(Path("."))


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="apply_patch")
    p.add_argument("--patch", help="Path to PATCH_*.zip to apply (optional)")
    p.add_argument("--auto-reconcile", action="store_true", help="If certify detects drift, reconcile index + rebuild + re-verify.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_root()
    args = parse_args(argv)

    # Enforce Windows-first EOL policy (repo-local) to avoid CRLF/LF staging blocks.
    # Safe no-op when .git is not present (e.g. zip snapshot).
    try:
        run([sys.executable, "scripts/git_eol_policy.py", "--apply", "--format", "line"])
    except Exception:
        pass

    if args.patch:
        print(f"APPLY_PATCH unzip {args.patch}")
        apply_zip(Path(args.patch))

    print("APPLY_PATCH run gates")
    rc = run([sys.executable, "tools/run_gates.py"])
    if rc == 0:
        return 0

    # Auto-reconcile is intended for the step-system drift (certify_steps rc=10)
    # AND for common patch-application flows where MANIFEST must be rebuilt to include newly introduced tracked files.
    if rc in (2, 10) and args.auto_reconcile:
        print("AUTO_RECONCILE running reconcile_step_index + rebuild_manifest + verify_manifest + certify_steps")
        r1 = run([sys.executable, "tools/reconcile_step_index.py"])
        if r1 != 0:
            return r1
        r2 = run([sys.executable, "tools/rebuild_manifest.py"])
        if r2 != 0:
            return r2
        r3 = run([sys.executable, "tools/verify_manifest.py"])
        if r3 != 0:
            return r3
        r4 = run([sys.executable, "tools/certify_steps.py"])
        return r4

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
