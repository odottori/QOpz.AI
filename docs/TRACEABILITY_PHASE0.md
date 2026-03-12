# TRACEABILITY — Phase 0 (Gate 0) ↔ Control Framework v1.2

Questo documento fornisce una mappa **minima ma operativa** tra gli ID di controllo implementati nel validator (`P0-*`)
e gli ID/concetti del **QOAI_MASTER_CONTROL_FRAMEWORK_v1.2**.

> Obiettivo: migliorare auditability e “control trace” senza rinominare o riscrivere Phase 0.

## Mappa controlli

| Phase0 ID | Area | Descrizione sintetica | Framework v1.2 (equivalente) | Note operative |
|---|---|---|---|---|
| P0-A1 | BASE | Dirs/struttura minima (db/data/logs/reports/config) | QOAI-G0-002 (storage writable / runtime dirs) | Fail-fast CRITICAL |
| P0-A2 | BASE | Presenza lockfile (requirements.lock) | QOAI-G0-008 (dependency lock present) / QOAI-REL-* (repro baseline) | Nota: la coerenza lock verrà rafforzata in Fase 1 evoluta |
| P0-A3 | BASE | Config load/parse (toml/json) | QOAI-G0-001 (profiles) + QOAI-G0-003 (config validity) | In caso di errore: exit 10 |
| P0-A4 | BASE | Env & dependency preflight (Python + deps per profilo) | QOAI-G0-008 (dependency contract) | dev: optional deps SKIP; paper/live: deps required |
| P0-A5 | BASE | Secrets leak scan (config) | QOAI-G0-007 (no secrets in config/artifacts) | Warning/critical a seconda profilo (se previsto) |
| P0-B1 | BASE | DuckDB writable | QOAI-G0-002 (storage writable) | |
| P0-B2 | BASE | DB schema marker presente | QOAI-G0-002 (schema applied marker) | Dipende da scripts/init_db.py |
| P0-B3 | BASE | DuckDB open + basic query | QOAI-G0-002 | |
| P0-C1 | DATA | Dataset seed deterministico (config) | QOAI-G0-003 (deterministic dataset) | |
| P0-D1 | BROKER | IB connectivity check | QOAI-G0-004 (broker connectivity) | In paper/live CRITICAL |
| P0-D2 | BROKER | Market data options check | QOAI-G0-004 | In dev può essere SKIP se deps mancanti |
| P0-E1 | OPS | Logging path/write | QOAI-G0-006 (logging/reporting baseline) | |
| P0-E2 | OPS | Kill-switch / safety flag | QOAI-G0-009 (kill-switch present) | Formalizzazione completa in Domain 2 |

## Note di perimetro (MANIFEST / REGISTRO)
- `MANIFEST.txt` resta “CANON docs scope”.
- `REGISTRO_INTEGRITA.md` traccia anche file runtime/patch per audit interno.

