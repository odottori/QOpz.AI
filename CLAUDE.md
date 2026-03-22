# QOpz.AI — Claude Code Context

> Versione: v.T.11.13 | Root: `C:\.dev\QOpz.AI`

## Regola #1 — Leggi il planner PRIMA di qualsiasi azione

```bash
python scripts/planner_status.py --format line
```

Lo step attivo è in `planner/active_step.json`. Modificare solo file nei glob patterns
di `master_plan.json → scope_profiles[scope_profile]`. Violazioni di scope = STOP immediato.

---

## Struttura progetto

```
execution/          # Core: state machine, storage, adapters, paper metrics, reconcile
strategy/           # Scoring 4-pilastri, regime hardening, sizing controls
api/                # FastAPI: opz_api.py (preview/confirm, OCR, TTS, reporting)
scripts/            # Operativi: ingest, regime, IBKR OCR, healthcheck, planner tools
tests/              # Suite: test_d2_*.py (execution), test_f1..f6_*.py (fasi)
tools/              # Planner guard, manifest, gates
config/             # dev.toml, paper.toml, live.toml
planner/            # active_step.json, master_plan.json
.canonici/          # 00_MASTER.md → 04_APPENDICI.md (contratti canonici, NON modificare)
docs/               # Documentazione operativa
reports/            # Output validator (phase0_validation_*.json)
```

---

## Deploy cycle (ciclo completo)

Quando l'utente dice "deploya", "rebuilda", "push e rebuild" o simili, esegui in ordine:

```bash
# 1. Audit pre-commit
PYTHONIOENCODING=utf-8 python scripts/quick_audit.py --scope all --severity HIGH

# 2. TypeScript check
cd ui && npx tsc --noEmit && cd ..

# 3. Gates
python tools/planner_guard.py check --check-target index
python tools/run_gates.py --skip-manifest --skip-certify

# 4. Commit (conventional commits) + push
git add <file modificati>
git commit -m "tipo(scope): descrizione\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main

# 5. Rebuild VM (servizio nginx include UI React)
ssh -i ~/.ssh/qopz_vm_key -o StrictHostKeyChecking=no root@178.104.94.34 \
  "cd /opt/qopz && git pull origin main && \
   docker compose build --no-cache nginx && \
   docker compose up -d && docker compose ps"
```

---

## Avvio locale (sviluppo)

```bash
# API backend (porta 8765) — tieni aperto in un terminale dedicato
.venv\Scripts\python.exe -m uvicorn api.opz_api:app --port 8765 --reload

# UI React (porta 8173) — tieni aperto in un altro terminale
cd ui && npm run dev

# Poi apri: http://localhost:8173
```

> **Nota**: se la porta 8765 è occupata, usa `netstat -ano | findstr :8765` per trovare il PID
> e `taskkill /F /PID <PID>` in PowerShell (non in Git Bash).

---

## Allineamento VM (solo git pull, no rebuild)

Quando non ci sono modifiche a `ui/` o `Dockerfile.nginx`:

```bash
ssh -i ~/.ssh/qopz_vm_key -o StrictHostKeyChecking=no root@178.104.94.34 \
  "cd /opt/qopz && git pull origin main && docker compose ps"
```

---

## Comandi rapidi

```bash
# Stato planner
python scripts/planner_status.py

# Matrice avanzamento milestones
python scripts/advancement_matrix.py

# Healthcheck sistema
python scripts/healthcheck.py

# Gate validation (pre-commit obbligatorio)
python tools/planner_guard.py check --check-target index
python tools/run_gates.py --skip-manifest --skip-certify

# Test per dominio
python -m pytest tests/test_d2_*.py -v       # Execution domain
python -m pytest tests/test_f1_*.py -v       # F1 Data pipeline
python -m pytest tests/test_f2_*.py -v       # F2 Regime
python -m pytest tests/test_f3_*.py -v       # F3 Paper setup
python -m pytest tests/ -v                   # Tutti

# Validator Phase 0
python validator.py --profile dev

# Lock/sblocco step
python tools/planner_guard.py start --step-id F1-T5 --owner codex
python tools/planner_guard.py clear

# Reconciliation
python scripts/reconcile_execution.py --run-id <uuid> --profile dev
```

---

## Invarianti (mai violare)

| Invariante | Dettaglio |
|-----------|-----------|
| Human-in-the-loop | Sistema presenta, operatore conferma — no auto-execution |
| Preview/confirm token | Nessun ordine senza token esplicito via API |
| Event trail | Ogni transizione ordine → riga `order_events` |
| WFA anti-leakage | Soglie percentile IN-SAMPLE only, mai OOS |
| No market orders | SEMPRE limit + IBKR combo nativo (no gambe separate) |
| Kill switch | `ops/kill_switch.trigger` → arresto immediato |
| DATA_MODE watermark | Ogni report deve loggare `DATA_MODE` |
| Kelly gate | Solo con `DATA_MODE=VENDOR_REAL_CHAIN` AND `N_closed_trades≥50` |

---

## DATA_MODE — Regola non negoziabile

```
SYNTHETIC_SURFACE_CALIBRATED  →  Kelly DISABILITATO, watermark obbligatorio
VENDOR_REAL_CHAIN             →  Kelly ABILITATO solo se N_closed_trades ≥ 50
```

Ogni record DuckDB deve avere: `source_system`, `source_mode`, `source_quality`,
`run_id`, `asof_ts`, `received_ts`.

---

## Regime → Azioni

| Regime | Nuovi trade | Sizing |
|--------|-------------|--------|
| NORMAL | ✅ Tutte le strategie | 100% |
| CAUTION | ⚠️ Spread stretti + filtro dir. | 50% |
| SHOCK | ❌ STOP | 0% |

---

## Hard Filters (pre-score, eliminazione automatica)

`spread_pct > 10%` | `OI < 100` | `DTE < 14 o > 60` | `IVR < 20` | `margin > 30%`

---

## Piano milestones

```
R0_BASELINE        → D2.38–D2.43
R1_ENGINE_OFFLINE  → F1-T1..T4, F2-T1..T4
R1B_DEMO_PIPELINE  → F1-T5..T8, F2-T5          ← STEP ATTIVO: F1-T5
R2_PAPER_OPERATOR  → F3-T1, F3-T2, F6-T1
R3_PAPER_HEDGE     → F5-T1..T3
R4_GO_NO_GO        → F6-T2
R5_LIVE_ENABLE     → F6-T3
```

PT1_MICRO (€1k–2k) richiede: R0 + R1 + R1B + R2 + R3 + R4

---

## Validator exit codes

- `0` = PASS (certificato)
- `2` = WARNING (non blocca, non certifica)
- `10` = CRITICAL FAIL (blocca avanzamento milestone)

---

## Profili configurazione

- `dev` → config/dev.toml (DuckDB locale, dry-run adapter, dati sintetici)
- `paper` → config/paper.toml (IBKR paper, dati reali, no Kelly)
- `live` → config/live.toml (IBKR live, execution-grade)

---

## Vocabolario UI — Regola obbligatoria

I codici interni NON appaiono mai nell'interfaccia utente, nei testi visibili all'operatore,
né nelle discussioni su UX/design. Si usano SEMPRE i termini dell'UI già stabiliti.

| Codice interno / tecnico | Termine operativo da usare |
|--------------------------|----------------------------|
| `F1-T5`, `R1B`, `D2.38`, qualsiasi sigla planner | — (mai citare in UI) |
| `demo_pipeline` / `auto_demo_pipeline` | **pipeline dati** |
| `scan_full` / `opportunity scan` | **genera segnali** |
| `opportunity_candidates` | **segnali** |
| `premarketRows` / `universeItems` / `scanCandidates` | **segnali** |
| `universe_latest` / `universeLatest` | **universo** o **lista simboli** |
| `history_readiness` | **completezza storico** |
| `kelly_gate` / `kelly_enabled` | **soglia sizing** |
| `WFA`, `OOS`, `IS` | — (mai citare in UI) |
| `DTE` | **giorni alla scadenza** |
| `OI` | **open interest** (o abbreviato **OI** solo in tabelle) |
| `IVR` / `iv_rank` | **rango volatilità** (o **IVR** solo in tabelle) |
| `pnl_cumulative` | **P&L cumulato** |
| `compliance_violations` | **violazioni** |
| `go_nogo` / `goGate` | **accesso al mercato** |
| `source_system` / `data_mode` | **fonte dati** |
| `paper` profile | **simulazione** |
| `live` profile | **operativo** |

---

## Note operative

- Step lock attivo: modificare SOLO file nel `scope_profile` dello step corrente
- Pre-commit obbligatorio: `planner_guard.py check` + `run_gates.py`
- Non segnare step come completato senza evidenza (test pass + gate pass + report)
- Demo data (F1-T5..F2-T5): dedup + freshness skip + retention cap (no dump massivo)
- Estrazione LLM: validatore JSON deterministico obbligatorio prima dell'uso nel motore test
