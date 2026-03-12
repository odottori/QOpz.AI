# DB Residual Context (F1-T5)

Date: 2026-03-07
Branch: codex/integrate-recovered-v2
Policy: only DuckDB in runtime and active test/tooling paths.

## Summary
- Runtime status: DuckDB-only enforced.
- F1 scope code status: cleaned.
- Remaining mentions of legacy DB names are limited to historical snapshots and non-operational metadata.

## Residuals And Treatment

1. `.baseline_artifacts_vT11_1/*`
- Context: frozen legacy artifacts/snapshots.
- Operational impact: none.
- Treatment: keep as historical baseline, do not execute.

2. `.canonici/*`
- Context: canonical docs.
- Operational impact: none at runtime.
- Treatment: updated current wording to DuckDB-focused language.

3. `.qoaistate.json`
- Context: historical command notes.
- Operational impact: none.
- Treatment: wording normalized to current policy.

4. `rebuild_manifest.py` and `tools/rebuild_manifest.py`
- Context: extension filtering in manifest generation.
- Operational impact: none on runtime DB policy.
- Treatment: keep as generic hygiene unless you ask for strict text purge outside active scope.

## Verified Runtime/Tooling Paths (DuckDB-only)
- `execution/storage.py`
- `scripts/db_integrity.py`
- `scripts/market_data_ingest.py`
- `tools/f1_t4_db_integrity.py`
- `tests/test_f1_t4_db_integrity.py`
