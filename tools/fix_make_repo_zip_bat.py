from __future__ import annotations

import argparse
import base64
import subprocess
import sys
from pathlib import Path

# Embedded canonical bytes for make_repo_zip.bat (Windows CRLF), sourced from the validated file.
_EXPECTED_B64 = "QGVjaG8gb2ZmDQpzZXRsb2NhbCBFbmFibGVFeHRlbnNpb25zDQoNClJFTSBVc2FnZTogbWFrZV9yZXBvX3ppcF9sb2NhbC5iYXQgW1JFUE9fRElSXSBbUkVGXQ0KUkVNIERlZmF1bHRzOiBSRVBPX0RJUiA9IGN1cnJlbnQgc2NyaXB0IGRpciwgUkVGID0gSEVBRA0KDQpzZXQgIlJFUE9fRElSPSV+MSINCmlmICIlUkVQT19ESVIlIj09IiIgc2V0ICJSRVBPX0RJUj1DOlwuZGV2XFF1YW50T3B6aW9uaS5BSSINCg0Kc2V0ICJSRUY9JX4yIg0KaWYgIiVSRUYlIj09IiIgc2V0ICJSRUY9SEVBRCINCg0KZm9yIC9mICUlaSBpbiAoJ3Bvd2Vyc2hlbGwgLU5vUHJvZmlsZSAtQ29tbWFuZCAiR2V0LURhdGUgLUZvcm1hdCB5eXl5TU1kZF9ISG1tc3MiJykgZG8gc2V0ICJUUz0lJWkiDQpzZXQgIk9VVFpJUD0lfmRwMFF1YW50T3B6aW9uaS5BSV9yZXBvXyVUUyUuemlwIg0KDQpjZCAvZCAiJVJFUE9fRElSJSIgfHwgKGVjaG8gW0VSUk9SXSBSZXBvIGRpciBub24gdHJvdmF0bzogJVJFUE9fRElSJSAmIGV4aXQgL2IgMSkNCg0KZ2l0IHJldi1wYXJzZSAtLWlzLWluc2lkZS13b3JrLXRyZWUgPm51bCAyPiYxIHx8IChlY2hvIFtFUlJPUl0gTm9uIGUnIHVuYSByZXBvIGdpdDogJVJFUE9fRElSJSAmIGV4aXQgL2IgMSkNCg0KZm9yIC9mICUlcyBpbiAoJ2dpdCBzdGF0dXMgLS1wb3JjZWxhaW4nKSBkbyAoDQogIGVjaG8gW0VSUk9SXSBXb3JraW5nIHRyZWUgTk9OIHB1bGl0YS4gQ29tbWl0dGEvc3Rhc2hhIHByaW1hIGRpIHppcHBhcmUuDQogIGV4aXQgL2IgMQ0KKQ0KDQplY2hvIFtJTkZPXSBBcmNoaXZpbmcgcmVmOiAlUkVGJQ0KaWYgZXhpc3QgIiVPVVRaSVAlIiBkZWwgL3EgIiVPVVRaSVAlIg0KDQpnaXQgYXJjaGl2ZSAtLWZvcm1hdD16aXAgLS1vdXRwdXQgIiVPVVRaSVAlIiAlUkVGJSB8fCAoZWNobyBbRVJST1JdIGdpdCBhcmNoaXZlIGZhbGxpdG8uICYgZXhpdCAvYiAxKQ0KDQplY2hvIFtPS10gWklQIGNyZWF0bzogJU9VVFpJUCUNCmV4aXQgL2IgMA0K"

def expected_bytes() -> bytes:
    return base64.b64decode(_EXPECTED_B64.encode("ascii"))


def _ensure_repo_root() -> None:
    required = ["validator.py", ".qoaistate.json"]
    missing = [p for p in required if not Path(p).exists()]
    if missing:
        raise SystemExit(f"ERROR: not repo root (missing: {', '.join(missing)})")


def _write_make_repo_zip() -> None:
    Path("make_repo_zip.bat").write_bytes(expected_bytes())


def _handle_alias(keep_alias: bool) -> None:
    alias = Path("make_repo0_zip.bat")
    if not alias.exists():
        return
    if keep_alias:
        # Keep it but ensure content matches (idempotent).
        alias.write_bytes(expected_bytes())
    else:
        alias.unlink()


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="fix_make_repo_zip_bat")
    p.add_argument("--keep-alias", action="store_true", help="Keep make_repo0_zip.bat (default: delete it).")
    p.add_argument("--no-rebuild-manifest", action="store_true", help="Do not rebuild/verify manifest after the fix.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_root()
    args = parse_args(argv)

    print("FIX make_repo_zip.bat -> canonical local script")
    _write_make_repo_zip()

    if Path("make_repo0_zip.bat").exists():
        if args.keep_alias:
            print("KEEP alias make_repo0_zip.bat (syncing content)")
        else:
            print("DELETE legacy alias make_repo0_zip.bat")
        _handle_alias(keep_alias=args.keep_alias)

    if not args.no_rebuild_manifest:
        if Path("tools/rebuild_manifest.py").exists():
            print("REBUILD_MANIFEST")
            rc = _run([sys.executable, "tools/rebuild_manifest.py"])
            if rc != 0:
                print(f"FAIL rebuild_manifest rc={rc}")
                return rc
        if Path("tools/verify_manifest.py").exists():
            print("VERIFY_MANIFEST")
            rc = _run([sys.executable, "tools/verify_manifest.py"])
            if rc != 0:
                print(f"FAIL verify_manifest rc={rc}")
                return rc

    print("OK fix_make_repo_zip_bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
