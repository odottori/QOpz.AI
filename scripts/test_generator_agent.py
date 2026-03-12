"""Test Generator Agent (D2.60).

Low-overhead helper that maps changed files to the most relevant unittest modules
and can optionally scaffold minimal failing-safe test stubs for unmapped Python files.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Iterable


EXACT_TEST_MAP: dict[str, list[str]] = {
    "scripts/healthcheck.py": ["tests/test_d2_19_healthcheck.py"],
    "scripts/progress_report.py": ["tests/test_d2_23_progress_report.py"],
    "scripts/repo_sync_status.py": ["tests/test_d2_35_repo_sync_status.py"],
    "scripts/submit_order.py": [
        "tests/test_d2_18_submit_preflight_scope.py",
        "tests/test_d2_20_dataset_mode_guard.py",
        "tests/test_d2_21_dataset_profile_consistency.py",
        "tests/test_d2_22_submit_dataset_mode_guard.py",
    ],
    "validator.py": [
        "tests/test_d2_20_dataset_mode_guard.py",
        "tests/test_d2_21_dataset_profile_consistency.py",
    ],
}

PREFIX_TEST_MAP: dict[str, list[str]] = {
    "config/": [
        "tests/test_d2_20_dataset_mode_guard.py",
        "tests/test_d2_21_dataset_profile_consistency.py",
        "tests/test_d2_22_submit_dataset_mode_guard.py",
    ],
}


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip()


def infer_test_modules(changed_files: Iterable[str]) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    unmapped: list[str] = []

    for raw in changed_files:
        path = _normalize(raw)
        if not path:
            continue

        mapped = False
        if path in EXACT_TEST_MAP:
            selected.extend(EXACT_TEST_MAP[path])
            mapped = True

        for prefix, tests in PREFIX_TEST_MAP.items():
            if path.startswith(prefix):
                selected.extend(tests)
                mapped = True

        if not mapped and path.endswith(".py") and not path.startswith("tests/"):
            unmapped.append(path)

    return sorted(set(selected)), sorted(set(unmapped))


def build_unittest_command(test_modules: list[str]) -> str:
    if not test_modules:
        return "python -m unittest -v"
    return "python -m unittest -v " + " ".join(test_modules)


def guess_stub_test_path(source_path: str) -> str:
    src = Path(source_path)
    return str(Path("tests") / f"test_auto_{src.stem}.py")


def render_stub_test(source_path: str) -> str:
    module_name = Path(source_path).stem
    return f'''import unittest\n\n\nclass TestAuto_{module_name}(unittest.TestCase):\n    def test_placeholder(self):\n        self.assertTrue(True)\n\n\nif __name__ == "__main__":\n    unittest.main()\n'''


def write_stub_tests(unmapped_sources: list[str]) -> list[str]:
    created: list[str] = []
    for src in unmapped_sources:
        target = Path(guess_stub_test_path(src))
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_stub_test(src), encoding="utf-8")
        created.append(str(target))
    created = [str(x).replace("\\", "/") for x in created]
    return created


def changed_files_from_git(from_ref: str, to_ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{from_ref}..{to_ref}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="test_generator_agent")
    p.add_argument("--changed-file", action="append", default=[], help="Changed file path (repeatable)")
    p.add_argument("--from-ref", default=None, help="Git from-ref for auto diff mode")
    p.add_argument("--to-ref", default="HEAD", help="Git to-ref for auto diff mode")
    p.add_argument("--write-stubs", action="store_true", help="Create placeholder tests for unmapped Python files")
    p.add_argument("--fail-on-unmapped", action="store_true", help="Return exit 10 when unmapped python files are found")
    p.add_argument("--run", action="store_true", help="Run recommended test command and include run result")
    p.add_argument("--format", choices=["json", "md"], default="json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    changed_files = list(args.changed_file)
    if not changed_files and args.from_ref:
        changed_files = changed_files_from_git(args.from_ref, args.to_ref)

    test_modules, unmapped = infer_test_modules(changed_files)
    generated = write_stub_tests(unmapped) if args.write_stubs else []
    cmd = build_unittest_command(test_modules + generated)

    final_exit_code = 0
    run_result: dict[str, object] | None = None

    if args.run:
        proc = subprocess.run(shlex.split(cmd), check=False, capture_output=True, text=True)
        run_result = {
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        if proc.returncode != 0:
            final_exit_code = 10

    if args.fail_on_unmapped and unmapped:
        final_exit_code = 10

    payload = {
        "changed_files": changed_files,
        "selected_test_modules": test_modules,
        "unmapped_python_files": unmapped,
        "generated_test_stubs": generated,
        "recommended_test_command": cmd,
        "fail_on_unmapped": bool(args.fail_on_unmapped),
        "run_requested": bool(args.run),
        "run_result": run_result,
        "final_exit_code": final_exit_code,
    }

    if args.format == "md":
        lines = [
            "# Test Generator Agent",
            "",
            f"- Changed files: {len(changed_files)}",
            f"- Selected test modules: {len(test_modules)}",
            f"- Unmapped python files: {len(unmapped)}",
            f"- Final exit code: {final_exit_code}",
            "",
            "## Recommended command",
            f"`{cmd}`",
        ]
        if test_modules:
            lines.extend(["", "## Selected tests"])
            lines.extend([f"- {t}" for t in test_modules])
        if unmapped:
            lines.extend(["", "## Unmapped python files"])
            lines.extend([f"- {f}" for f in unmapped])
        if generated:
            lines.extend(["", "## Generated stubs"])
            lines.extend([f"- {g}" for g in generated])
        if run_result is not None:
            lines.extend(["", "## Run result", f"- Exit code: {run_result['exit_code']}"])
        print("\n".join(lines))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return int(final_exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
