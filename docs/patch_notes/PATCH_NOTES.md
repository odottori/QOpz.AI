# Hotfix — __future__ import ordering (validator.py)

Fixes:
- `from __future__ import annotations` must be the first statement in the module.
- This hotfix reorders the import to comply with Python syntax.

Apply:
- Overwrite `validator.py` in the project root.


---

# Patch — Fase 1 (Environment & Dependency Layer)

Build: 2026-02-24 18:24:41 UTC

Changes:
- Added explicit requirements sets: `requirements-core.txt`, `requirements-broker-ib.txt`, `requirements-dev.txt`.
- Added Phase 0 preflight for env/deps (`P0-A4`).
- Dev profile now **skips** IBKR checks when `ib_insync` is not installed (no warning downgrade).
- Paper/Live remain blocking if `ib_insync` is missing.
- Updated `03_SETUP.md` with PowerShell install commands.


---

# Patch — Fase 1.4 (Traceability + Report Hygiene)

Build: 2026-02-24 19:45:00 UTC

Changes:
- Added Phase 0 ↔ Framework v1.2 traceability map: `docs/TRACEABILITY_PHASE0.md`.
- Report JSON metadata:
  - `generated_at_utc`, `results_count`, `execution_mode`, `fail_fast_reason`.
- Report hygiene (non-breaking):
  - Added `severity_on_fail` and `severity_effective` per result to avoid ambiguity when `status=PASS`.

Notes:
- No changes to PASS/FAIL logic or exit code policy.
