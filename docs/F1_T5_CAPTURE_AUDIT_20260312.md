# F1-T5 Capture Audit (2026-03-12)

## Scope

Active step: `F1-T5`
Milestone: `R1B_DEMO_DATA_PIPELINE`

This note records the current safe cleanup posture while continuing work on the capture stage.

## Core for current step

- `scripts/capture_pages.py`
- `scripts/demo_pipeline_lib.py`
- `tests/test_f1_t5_capture_pages.py`
- `docs/DEMO_DATA_PIPELINE_PLAN.md`
- `planner/master_plan.json`
- `planner/active_step.json`

## Behavior verified in this delta

- Capture persists raw artifacts on first ingest.
- Duplicate payloads are skipped deterministically by fingerprint.
- Fresh captures within the configured freshness window are skipped.
- Structured capture log now records `captured`, `duplicate`, `skipped_fresh`, and aggregate `pruned` events.
- Summary now includes `bytes_on_disk` for low-footprint monitoring.

## Cleanup classification

### Keep as core runtime or project control

- `api/`
- `execution/`
- `ui/`
- `scripts/`
- `tools/`
- `tests/`
- `planner/`
- `config/`
- `docs/`
- `samples/`

### Keep for now, classify as historical or handoff support

- `.canonici/`
- `.baseline_artifacts_vT11_1/`
- `.quarantine/`
- `PATCH_NOTES.md`
- `PROMPT_*`
- `Prepare_QOpzAI_Handoff.ps1`

### Candidate cleanup or quarantine in a later safe delta

- `qopz_work/`
  - appears to duplicate active project code and tests; verify divergence before removal.
- `QOpz.AI - Progetto Opportunity Scanner.html`
- `QOpz.AI - Progetto Opportunity Scanner_files/`
  - large exported handoff material, useful as archive but not as active runtime source.
- ad hoc temp folders such as `.tmp_test/`
  - keep out of source control and clean periodically.

## Rule for next cleanup pass

Do not delete duplicated or historical folders until they are classified against the active runtime paths and the current git baseline.
Prefer a documented quarantine or ignore decision before removal.
