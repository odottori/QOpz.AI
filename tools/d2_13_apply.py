from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rebuild_manifest import rebuild_manifest


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_state() -> None:
    p = Path(".qoaistate.json")
    st = json.loads(p.read_text(encoding="utf-8"))
    st.setdefault("steps_completed", [])
    if "D2.13" not in st["steps_completed"]:
        st["steps_completed"].append("D2.13")

    st["next_step"] = "D2.14"
    st.setdefault("decisions_approved", [])
    st["decisions_approved"].append(
        {
            "ts_utc": _utc(),
            "id": "D2.13_ACK_TIMEOUT_TAXONOMY",
            "summary": "Introduced Gate0-safe ACK/timeout taxonomy and broker-event mapping (paper/live ready).",
        }
    )
    st.setdefault("acceptance", [])
    st["acceptance"].append(
        {
            "ts_utc": _utc(),
            "step": "D2.13",
            "commands": [
                r"py .\validator.py --profile dev --config .\config\dev.toml",
                r"py -m unittest -v",
            ],
            "expected_exit": {"validator": 0, "unittest": 0},
        }
    )
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_docs() -> None:
    p = Path("docs/QOAI_MASTER_CONTROL_FRAMEWORK_v1.2.md")
    if not p.exists():
        return
    txt = p.read_text(encoding="utf-8", errors="replace")
    marker = "## CONTROL DOMAIN 2"
    if marker not in txt:
        return
    if "D2.13 — ACK/Timeout taxonomy" in txt:
        return

    insert = "\n### D2.13 — ACK/Timeout taxonomy (paper/live Gate0-safe)\n" \
             "- Canonical intent: QOAI-EXE-004 (ACK classification) / QOAI-EXE-005 (event trail consistency)\n" \
             "- Implementation: execution/ack_taxonomy.py (AckStatus, classify_ack_status, map_broker_event)\n" \
             "- Tests: tests/test_d2_13_ack_taxonomy_paperlive.py\n"
    # append near end of Domain 2 section (simple: append at end of file)
    p.write_text(txt.rstrip() + "\n" + insert + "\n", encoding="utf-8")


def update_registro() -> None:
    p = Path(".canonici/REGISTRO_INTEGRITA.md")
    if not p.exists():
        return
    entry = (
        f"\n## Build {_utc()} — D2.13\n"
        "- Added ACK/timeout taxonomy module + unit tests (Gate0-safe paper/live).\n"
        "- Updated .qoaistate.json (step + acceptance).\n"
        "- Updated docs/QOAI_MASTER_CONTROL_FRAMEWORK_v1.2.md (Domain 2 trace).\n"
    )
    p.write_text(p.read_text(encoding="utf-8", errors="replace").rstrip() + entry + "\n", encoding="utf-8")


def main() -> int:
    update_state()
    update_docs()
    update_registro()
    rebuild_manifest(Path(".canonici/MANIFEST.txt"))
    print("D2.13 applied: state/docs/registro updated; MANIFEST rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
