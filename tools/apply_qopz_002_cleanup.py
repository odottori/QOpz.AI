from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATCH_NOTES = [
    "PATCH_NOTES.md",
    "PATCH_NOTES_D2_0.md",
    "PATCH_NOTES_D2_1.md",
    "PATCH_NOTES_D2_1_1.md",
    "PATCH_NOTES_D2_1_3.md",
    "PATCH_NOTES_D2_2.md",
    "PATCH_NOTES_D2_2_1.md",
    "PATCH_NOTES_D2_2_2.md",
    "PATCH_NOTES_QOpz.AI_001.md",
]

QUARANTINE_SCRIPTS = [
    "build_tesseract_json.py",
    "ibkr_ocr_paddle_extract.py",
    "ibkr_screen_to_inbox.py",
    "ibkr_uia_extract.py",
    "ibkr_vision_extract_ollama.py",
]

DELETE_ROOT_ONLY = [
    "fix_portable_snapshot.py",
    "rebuild_manifest.py",
]


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _move_if_present(src: Path, dst: Path, actions: list[str]) -> None:
    if not src.exists():
        return
    _ensure_parent(dst)
    if dst.exists():
        src.unlink()
        actions.append(f"delete duplicate {src.as_posix()}")
        return
    shutil.move(str(src), str(dst))
    actions.append(f"move {src.as_posix()} -> {dst.as_posix()}")


def _delete_file_if_present(path: Path, actions: list[str]) -> None:
    if path.exists() and path.is_file():
        path.unlink()
        actions.append(f"delete {path.as_posix()}")


def _delete_pycache_and_pyc(actions: list[str]) -> None:
    pyc_count = 0
    for p in ROOT.rglob("*.pyc"):
        try:
            p.unlink()
            pyc_count += 1
        except FileNotFoundError:
            pass
    if pyc_count:
        actions.append(f"delete {pyc_count} .pyc files")

    removed_dirs = 0
    for p in sorted(ROOT.rglob("__pycache__"), reverse=True):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed_dirs += 1
    if removed_dirs:
        actions.append(f"delete {removed_dirs} __pycache__ dirs")


def _clean_reports(actions: list[str]) -> None:
    reports = ROOT / "reports"
    if not reports.exists():
        return
    removed = 0
    for p in reports.glob("phase0_validation_*"):
        if p.is_file():
            p.unlink()
            removed += 1
    if removed:
        actions.append(f"delete {removed} derived report files")


def main() -> int:
    actions: list[str] = []

    patch_dir = ROOT / "docs" / "patch_notes"
    for name in PATCH_NOTES:
        _move_if_present(ROOT / name, patch_dir / name, actions)

    _move_if_present(
        ROOT / "PROMPT PROSEGUI.txt",
        ROOT / "docs" / "archive" / "prompts" / "PROMPT_PROSEGUI.txt",
        actions,
    )

    quarantine_dir = ROOT / ".quarantine" / "scripts"
    for name in QUARANTINE_SCRIPTS:
        _move_if_present(ROOT / "scripts" / name, quarantine_dir / name, actions)

    for name in DELETE_ROOT_ONLY:
        _delete_file_if_present(ROOT / name, actions)

    _clean_reports(actions)
    _delete_pycache_and_pyc(actions)

    if actions:
        print("QOPZ_002_CLEANUP_OK")
        for item in actions:
            print(f"- {item}")
    else:
        print("QOPZ_002_CLEANUP_NOOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
