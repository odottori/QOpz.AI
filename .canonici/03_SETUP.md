# QuantOptionAI — SETUP (Phase 0 + Automazione)
_Versione: v.T.11.13

---

## 1) TODO Phase 0 (fonte normativa)

Questa TODO è una **lista eseguibile**: ogni item ha una validazione automatica.
Spec del validator: `04_APPENDICI.md (sezione Validator CLI)`.

## Convenzioni
- Stato: `TODO | DOING | DONE | BLOCKED`
- Severità: `CRITICAL | HIGH | MEDIUM | LOW`
- Un CRITICAL in FAIL blocca l’avanzamento.

## Installazione dipendenze (PowerShell)

> Nota: Phase 0 in **dev** non richiede `ib_insync`. In **paper/live** è richiesto.

Core (tutti i profili):
```powershell
py -m pip install -r .\requirements-core.txt
```

Paper/Live (abilita broker IBKR):
```powershell
py -m pip install -r .\requirements-core.txt
py -m pip install -r .\requirements-broker-ib.txt
```

Dev/QA (opzionale):
```powershell
py -m pip install -r .\requirements-dev.txt
```

## A) Base (comune)
- [ ] (P0-001) **CRITICAL** Cartelle: db/, data/, logs/, reports/, config/ (DEV/PAPER/LIVE)
- [ ] (P0-002) **CRITICAL** Python env + lock dipendenze (DEV/PAPER/LIVE)
- [ ] (P0-003) **CRITICAL** Config profili `dev/paper/live` (DEV/PAPER/LIVE)
- [ ] (P0-004) **CRITICAL** Secrets via env vars / vault locale (PAPER/LIVE)

## B) Storage / DuckDB
- [ ] (P0-010) **CRITICAL** DuckDB creato + schema applicato (DEV/PAPER/LIVE)
- [ ] (P0-011) Layout Parquet partizionato + convention `asof_ts` (DEV/PAPER/LIVE)
- [ ] (P0-012) Lineage obbligatoria: `source_system/source_mode/source_quality/run_id/asof_ts/received_ts` (DEV/PAPER/LIVE)

## C) Dataset sintetico (mockup)
- [ ] (P0-020) **CRITICAL** Generatore synthetic: underlying + VIX proxy + chain coerente (DEV)
- [ ] (P0-021) Seed deterministico + versioning dataset (DEV)

## D) Broker / Market Data (paper)
- [ ] (P0-030) **CRITICAL** IBKR API stabile (keepalive) (PAPER)
- [ ] (P0-031) **CRITICAL** Market data real-time opzioni attivo (PAPER)

## E) Ops / Sicurezza
- [ ] (P0-040) **CRITICAL** Logging strutturato + rotation (DEV/PAPER/LIVE)
- [ ] (P0-041) **CRITICAL** Kill-switch dry run (DEV/PAPER)

## GO/NO-GO Phase 0
- GO se tutti i CRITICAL PASS
- NO-GO altrimenti

## 2) Validator automation (spec)

Obiettivo: la TODO Phase 0 diventa un **processo automatico** che:
1) bootstrap (crea ciò che manca)  2) validate  3) produce report firmabile (hash)

## Input
- `01_PHASE0_TODO.md`
- `config.(toml|yaml)` + env vars

## Output
- `reports/phase0_validation_<run_id>.json`
- `reports/phase0_validation_<run_id>.md`
- stampa hash SHA256 del report

## Regole
- CRITICAL FAIL ⇒ FAIL globale
- non-CRITICAL FAIL ⇒ warning

## Contract JSON (minimo)
```json
{
  "run_id": "uuid",
  "timestamp": "2026-02-24T..",
  "profile": "dev|paper|live",
  "results": [
    {"id":"P0-010","status":"PASS|FAIL","severity":"CRITICAL","details":"..."} 
  ],
  "summary": {"pass":0,"fail":0,"warn":0},
  "sha256":"..."
}
```

## 3) DuckDB + Dati sintetici + Lineage (obbligatori)

- DuckDB è la scelta primaria per DEV e consigliata fino a single-user/paper.
- In DEV è raccomandato usare **dati sintetici** per mockup end-to-end.
- Ogni tabella chiave deve includere campi di **provenienza** (lineage) per audit e gating.

### Lineage fields minimi

- `source_system` (SYNTH/IBKR/…)
- `source_mode` (synthetic/historical/paper/live)
- `source_quality` (gold/silver/bronze/unknown)
- `run_id` (uuid)
- `asof_ts` (timestamp di mercato)
- `received_ts` (timestamp ricezione)


\
    ## Gate 0 — Phase 0 Validation (obbligatorio)

    La Phase 0 è il gate di ingresso **non opzionale** prima di qualsiasi operazione (anche paper).
    Produce un report certificabile (JSON + SHA256) e blocca su CRITICAL FAIL.

    PowerShell:
    ```powershell
    py .\scripts\init_db.py --config .\config\paper.toml
    py .\scripts\validate_phase0.ps1 -Profile paper -Config .\config\paper.toml -Capital 5000
    echo $LASTEXITCODE
    ```
    Exit codes: 0 PASS | 2 WARNING only | 10 CRITICAL FAIL.

    Policy broker connectivity (Phase 0):
    - dev: WARNING
    - paper: CRITICAL
    - live: CRITICAL
