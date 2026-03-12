"""D2.14 apply helper.

Updates:
  - .qoaistate.json (step completion + acceptance placeholders)
  - docs/QOAI_MASTER_CONTROL_FRAMEWORK_v1.2.md (adds anchors to D2.14)
  - .canonici/REGISTRO_INTEGRITA.md (appends entry)
  - .canonici/MANIFEST.txt (rebuild)

Run from repo root:
  py -m tools.d2_14_apply
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rebuild_manifest import rebuild_manifest


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_registro(entry: str) -> None:
    p = Path(".canonici/REGISTRO_INTEGRITA.md")
    if not p.exists():
        return
    txt = p.read_text(encoding="utf-8")
    if not txt.endswith("\n"):
        txt += "\n"
    txt += entry
    if not txt.endswith("\n"):
        txt += "\n"
    p.write_text(txt, encoding="utf-8")


def _touch_docs() -> None:
    p = Path("docs/QOAI_MASTER_CONTROL_FRAMEWORK_v1.2.md")
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    marker = "## CONTROL DOMAIN 2"
    if marker not in t:
        return

    add = (
        "\n\n### D2.14 — Broker Event Schema + Normalization\n"
        "- Adds `execution/broker_event_schema.py` to define a minimal broker event schema and a deterministic normalization mapping to internal event types (Gate0-safe).\n"
        "- Updates ACK taxonomy to reference canonical internal event types.\n"
    )

    if "D2.14 — Broker Event Schema + Normalization" not in t:
        # Insert after CONTROL DOMAIN 2 header
        parts = t.split(marker, 1)
        t = parts[0] + marker + add + parts[1]
        p.write_text(t, encoding="utf-8")


def main() -> int:
    # Update state
    sp = Path(".qoaistate.json")
    if sp.exists():
        st = _load_json(sp)
    else:
        st = {}

    st.setdefault("steps_completed", [])
    if "D2.14" not in st["steps_completed"]:
        st["steps_completed"].append("D2.14")

    st.setdefault("decisions_approved", [])
    dec = {
        "id": "D2.14",
        "ts_utc": _utc_now(),
        "title": "Broker event schema + deterministic normalization (Gate0-safe)",
        "notes": [
            "Introduce execution/broker_event_schema.py with InternalEventType enum used across taxonomy.",
            "Keep mapping pure/no I/O; adapters can plug raw events later without refactors.",
        ],
    }
    st["decisions_approved"].append(dec)

    st.setdefault("acceptance", [])
    st["acceptance"].append(
        {
            "ts_utc": _utc_now(),
            "commands": [
                "py .\\validator.py --profile dev --config .\\config\\dev.toml",
                "py -m unittest -v",
            ],
            "exit_codes": {"validator": None, "unittest": None},
        }
    )
    st["next_step"] = "D2.15"
    _save_json(sp, st)

    # Update docs (derived)
    _touch_docs()

    # Registro entry
    _append_registro(
        f"\n- {_utc_now()} — D2.14: broker event schema + normalization; ack taxonomy aligned to InternalEventType; added unit tests.\n"
    )

    # Rebuild manifest deterministically
    rebuild_manifest(Path('.canonici/MANIFEST.txt'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
