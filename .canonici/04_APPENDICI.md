# QuantOptionAI — APPENDICI (Operative + Advanced)
_Versione: v.T.11.13

---

## Appendice A — Walkthrough Operativo

# Appendice A — Walkthrough Operativo End-to-End (CET)
_Data: 2026-02-24_

Scenario completo: Entry → Monitoraggio → Hedge → Exit → Journal (conto €5.000).

## Timeline (CET)
- 14:30: pre-market checks (regime, No-Trade, TCC)
- 15:35–15:50: entry window (smart ladder)
- 16:30 / 19:30: monitoraggio
- Giorno+1 15:00: shock trigger (VIX spike + p_shock↑ + DD≥10%)
- Giorno+1 15:20: hedge (put spread OTM 30–60 DTE) nel vincolo costo ≤20% del credito medio

> **AVVISO (didattico, non operativo):** esempi “budget hedge = 20% del credito” sono solo illustrativi.  
> **Riferimento primario in produzione:** policy *scenario-based* (Base/Shock) con metodo di stima via scenari VIX storici T5.3 applicati al P&L corrente.
- 22:15: journaling (reason_code obbligatorio)

> **Nota v.T.11.3 (illustrativo):** l’esempio “budget hedge = 20% del credito” è didattico. Su sottostanti liquidi (SPY/IWM) e OTM 30–60 DTE, un budget molto basso può non acquistare protezione significativa. In produzione si usa un budget hedge più alto **oppure** un delta overlay dinamico (vedi policy strumenti).

## Numeri esempio
- Credit spread: $0.45, width 5$ → max risk ≈ $455 per 1-lot
- TCC stimato: $0.12 → 3×TCC=$0.36 → entry OK
- Hedge target costo: ≤20% di $45 → ≤$9 (scegliere strikes per rientrare)

## Appendice B — Moduli Avanzati (Non Canonici)

# Appendice B — Moduli Avanzati (Non Canonici): Delta Overlay
_Data: 2026-02-24_

## Lockout (obbligatorio)
Delta Overlay consentito solo se:
- Capitale ≥ €10.000
- ≥6 mesi live/paper con disciplina OK
- costi sotto controllo
Altrimenti: DISABILITATO.

## Scopo
Hedge direzionale parziale (delta 0.2–0.3 del delta netto portafoglio) con ETF, rebalancing 1–2 volte/giorno.

## Nota
Non sostituisce il kill-switch; se DD≥15% stop + chiusura overlay.

## Stato integrazioni memo (baseline)

# Stato integrazioni Memo (v11.1 Enhanced)
1) ERD Mermaid + FK logiche: inserite (T7.1bis nel Tecnico).
2) Walkthrough end-to-end: aggiunta Appendice A (CET).
3) Delta Overlay: aggiunta Appendice B con lockout rigoroso.

CERTIFICATO



---

## v.T.11.3 — Policy strumenti hedge (Delta Overlay)

Strumenti ammessi (ordine preferenza):
1. Futures: ES/MES
2. ETF shares
3. ETF options

La scelta deve essere configurabile e documentata in run config (strumento, cost model, slippage, margin).

## v.T.11.3 — Wheel in regime SHOCK (gestione posizioni aperte)

In caso di regime switch verso **SHOCK**:
- nuove Wheel posizioni: **vietate**
- posizioni Wheel già aperte:
  - valutazione delta + exposure
  - hedge overlay se necessario
  - gestione/chiusura secondo risk cap e regole operative (no “set-and-forget”)

## Addendum v.T.11.4 — MICRO checklist (8 item)
1. Market data pipeline (underlying real) + calendari + logging
2. Regime classifier base (no HMM), con anti-leakage guard attivo
3. Strategia unica: Bull Put (IWM) con regole entry/exit semplici
4. Sizing fixed fractional (no Kelly)
5. Kill switch + risk caps
6. Journal (entry/exit/fees/slippage/margin used) + report KPI
7. Reconciliation giornaliera con statement broker (IBKR)
8. Test suite “lite gate” (Model/Ops)

## Addendum v.T.11.4 — Hedge: esempi scenari (template)
- Scenario Base: VIX +30% in 5 giorni → stimare X (loss) e verificare caps
- Scenario Shock: VIX +100% in 10 giorni → stimare Y (loss) e verificare caps
Metodo di stima: applicare gli scenari VIX storici definiti in T5.3 al P&L corrente del portafoglio tramite simulazione storica (historical shock replay).

Nota: il budget hedge è una conseguenza del vincolo su Y, non una % fissa del credito.

## Addendum v.T.11.4.1 — Esecuzione (MICRO)
Nel tier MICRO l’esecuzione può essere semplificata:
- ordine singolo (limit) con regole di aggressività controllata, oppure
- ladder aggressiva (pochi step) se spread/riempimento lo richiedono.
TWAP/VWAP è riservato al tier MEDIUM/ADVANCED ed è subordinato a validazione live (paper IBKR non è indicativo dei fill parziali).

## Addendum v.T.11.7 — Validator CLI (template report)

Template minimo `phase0_validation_<run_id>.json`:
```json
{
  "run_id": "YYYYMMDD_HHMMSS",
  "profile": "paper",
  "blocked": false,
  "exit_code": 0,
  "results": [
    {"id":"P0-001","severity":"CRITICAL","status":"PASS","details":"..."},
    {"id":"P0-010","severity":"WARNING","status":"FAIL","details":"..."}
  ]
}
```
SHA256 file `.sha256` = hash del JSON.

## Addendum v.T.11.7 — MICRO/SMALL: NO Kelly, sizing adattivo
- Pre-50 trade chiusi: usare Adaptive Fixed Fractional (regime-based), non Kelly.
- Kelly disponibile solo in MEDIUM/ADVANCED con vendor data + reconciliation + N≥50.

## Addendum v.T.11.7 — Correlation Breakdown: azione suggerita
Se `CORRELATION_BREAKDOWN` attivo:
- stop nuove posizioni short-vol
- ridurre sizing di posizioni aperte dove applicabile



### Allineamento Policy Execution

Nota: `00_MASTER.md` è il documento normativo; le presenti Appendici forniscono dettagli implementativi.


Nota: per il tier MICRO il protocollo aggiornato è definito in 00_MASTER.md (v.T.11.7+). 
TWAP/VWAP è riservato al tier MEDIUM/ADVANCED salvo diversa specifica futura.


Metodo stima: applicare scenari VIX da T5.3 al P&L del portafoglio corrente tramite simulazione storica (historical shock replay).


\
    ## Addendum v.T.11.13 — Phase 0 Validator (Gate 0)

    **Scopo:** gate di ingresso obbligatorio prima di trading (anche paper). Un solo CRITICAL FAIL → **NO-GO globale**.

    **Output:**
    - `reports/phase0_validation_<run_id>.json`
    - `reports/phase0_validation_<run_id>.md`
    - `reports/phase0_validation_<run_id>.sha256` (SHA256 del JSON)

    **Exit codes:** 0 PASS | 2 WARNING only | 10 CRITICAL FAIL (STOP).

    **Checklist normativa (MVP):**
    - BASE (CRITICAL): cartelle richieste; `requirements.lock`; config profilo; secrets guard (no hardcoded + env vars richieste)
    - STORAGE (CRITICAL/WARNING): duckdb path + marker `db/schema_applied.ok`; parquet convention (warning se assente)
    - DATASET (CRITICAL): synthetic generator smoke test + seed deterministico
    - BROKER + MARKET DATA (profilo-dipendente): dev=WARNING; paper/live=CRITICAL (connectivity + option bid/ask smoke test)
    - OPS (CRITICAL): logging scrivibile + rotation policy; kill-switch dryrun config presente

---

## Appendice C — Control Plane Operativo (IBWR + Observer) [v.T.11.14]

### Quando disabilitare IBKR (IBWR stop)

| Situazione | Azione consigliata |
|---|---|
| Manutenzione TWS/Gateway | `POST /opz/ibwr/service {"action":"stop"}` |
| Aggiornamento configurazione IBKR | stop → modifica → start |
| Sospetto malfunzionamento connessione | stop → verifica log → start |
| Fine giornata operativa | opzionale (sessione EOD la gestisce) |

Effetti di `IBWR stop`:
- Nuovi ordini bloccati (come soft kill switch)
- Posizioni aperte restano invariate su broker
- L'API rimane attiva (puoi monitorare, non eseguire)

### Observer Telegram — quando on/off

| Stato | Quando usarlo |
|---|---|
| `on` | Operatività normale — ricevi notifiche regime, briefing, errori |
| `off` | Manutenzione, test, rumore non desiderato |

Il kill switch forza `observer off` automaticamente — ricordare di riattivarlo dopo reset.

### Workflow manutenzione IBKR

```
1. observer off        (silenzio durante manutenzione)
2. ibwr stop           (blocca esecuzione)
3. ... modifica TWS/Gateway ...
4. ibwr start          (ripristina connessione)
5. verifica GET /opz/ibkr/status  (conferma porta 4001/4002 up)
6. observer on         (riattiva notifiche)
```

---

## Appendice D — Session Logs: Query di riferimento [v.T.11.14]

### Leggere sessioni dell'ultima settimana
```
GET /opz/session/logs?limit=14
```

### Diagnosticare sessioni con errori
```sql
SELECT session_date, session_type, trigger, errors_json
FROM session_logs
WHERE errors_json != '[]'
ORDER BY created_ts DESC
LIMIT 10;
```

### Rieseguire una sessione fallita manualmente
```
POST /opz/session/run
{"session_type": "morning"}
```
L'endpoint scrive una nuova riga in `session_logs` con `trigger = "manual"`.

---

## Appendice E — Contratti di comportamento su errore [v.T.11.14]

> Questa appendice definisce **cosa il sistema DEVE fare** in caso di errore su componenti critici.
> Non è un troubleshooting operativo — è un contratto normativo per implementatori.
> Violazioni di questi contratti rendono il run non certificabile.

---

### E.1 — Scheduler di sessione

| Condizione | Comportamento obbligatorio |
|---|---|
| Config `enabled=false` | Log `SESSION_SCHEDULER disabled` — nessun task creato — API rimane attiva |
| Config non parsabile (`SESSION_CFG_WARN`) | Log warning, scheduler non avviato, API non crasha |
| Sessione già in corso (`_SESSION_STATE["running"]=True`) | HTTP 409, messaggio `"Sessione già in corso — attendi il completamento"` — nessun secondo subprocess |
| Timeout subprocess (`duration_max_min` superato) | HTTP 504, log `SESSION_MORNING|EOD FAILED`, riga `session_logs` con `errors_json` popolato |
| Subprocess termina con errori non bloccanti | HTTP 200, log `SESSION_MORNING|EOD WARN errors=N`, riga `session_logs` con `errors_json` non vuoto |
| Subprocess termina con eccezione | Log `SESSION_MORNING|EOD FAILED: <exception>`, riga `session_logs` con stato di errore, API non crasha |
| IBKR non connesso durante EOD (equity snapshot) | Campo `equity=null` in `session_logs`, log warning, sessione considerata completata con warning |
| API offline all'orario schedulato | Sessione saltata senza riga in `session_logs` — comportamento atteso, non è un errore |

---

### E.2 — Control plane (IBWR / Observer / Kill switch)

| Condizione | Comportamento obbligatorio |
|---|---|
| Kill switch attivato | Blocco immediato esecuzione ordini — IBWR non può eseguire anche se `on` — log `KILL_SWITCH activated` |
| Kill switch attivato | Observer forzato `off` automaticamente — log `OBSERVER forced off` |
| IBWR stop | Nuovi ordini rifiutati — posizioni aperte invariate su broker — API resta attiva per monitoraggio |
| IBWR stop con kill switch attivo | Comportamento identico a kill switch — IBWR stop è ridondante ma non è un errore |
| Observer `on` senza Telegram configurato | Log warning `OBSERVER: Telegram not configured` — Observer rimane `off` — nessuna eccezione |
| Stato incoerente (IBWR on + kill switch on) | Kill switch ha priorità assoluta — `control_plane_ok=false` nel payload di stato |

---

### E.3 — DATA_MODE e Kelly gate

| Condizione | Comportamento obbligatorio |
|---|---|
| `DATA_MODE=SYNTHETIC_SURFACE_CALIBRATED` | Kelly DISABILITATO — sizing `adaptive_fixed_fractional` — watermark `NOT EXECUTION GRADE` obbligatorio su ogni report |
| `DATA_MODE=VENDOR_REAL_CHAIN` + `N_closed_trades < 50` | Kelly DISABILITATO — log `KELLY_GATE: N_trades insufficient` — sizing `adaptive_fixed_fractional` |
| Kelly abilitato senza gate soddisfatti | Condizione non ammessa — il sistema DEVE rifiutare il calcolo sizing Kelly e loggare come CRITICAL |
| `DATA_MODE` non presente in un record DuckDB | Record non valido — run non certificabile — CRITICAL in Phase 0 validator |

---

### E.4 — Dati e pipeline

| Condizione | Comportamento obbligatorio |
|---|---|
| IBKR offline durante ingest | Log `IBKR_OFFLINE`, chain options non aggiornata, `asof_ts` non avanzato — nessun crash |
| Chain options vuota per un simbolo | Simbolo escluso dallo scan con log warning — gli altri simboli processati normalmente |
| Latenza `asof_ts` > 30 min | Alert Telegram (se Observer on) + log `INGESTION_LATENCY_WARN` |
| Qualità dati sotto soglia (`source_quality` < B) | Candidato non ammesso allo scoring — hard filter — log per ogni esclusione |

---

### E.5 — Invarianti di errore (non negoziabili)

1. **Nessun componente critico deve crashare l'API** — ogni eccezione va catturata, loggata, e restituita come errore HTTP strutturato
2. **Ogni errore su un componente non blocca gli altri** — degradazione parziale, non arresto totale
3. **Ogni sessione deve scrivere una riga in `session_logs`** — anche in caso di errore parziale
4. **Kill switch ha priorità assoluta** — nessun meccanismo può bypassarlo, incluso IBWR
5. **Watermark DATA_MODE è obbligatorio** — la sua assenza è un CRITICAL FAIL nel validator

---

<!-- BEGIN GO_NOGO_RELEASE_PLAN -->
## Appendice Z — Roadmap GO/NO-GO (Release per moduli)

### Gate GO/NO-GO (paper → decisione live)
- Sharpe paper ≥ **0.8** (min **10** trade)
- Max DD paper < **8%** (in qualsiasi periodo)
- Violazioni regole (sizing/stop/no-trade): **ZERO**

### Gate upgrade Tier (OOS)
- Sharpe OOS > **0.8** · Max DD < **8%** · Violazioni **ZERO**

### Milestone per modulo
| Milestone | Soglia | Step richiesti |
|---|---|---|
| R0_BASELINE — Baseline operativa e integrità | dev | D2.38, D2.39, D2.40, D2.41, D2.42, D2.43 |
| R1_ENGINE_OFFLINE — Engine offline completo (Research-grade) | dev | F1-T1, F1-T2, F1-T3, F1-T4, F2-T1, F2-T2, F2-T3, F2-T4 |
| R1B_DEMO_DATA_PIPELINE — Data pipeline demo differita + estrazione LLM deterministica | dev | F1-T5, F1-T6, F1-T7, F1-T8, F2-T5 |
| R2_PAPER_OPERATOR — Paper trading operator-grade (Human-confirmed) | paper | F3-T1, F3-T2, F6-T1 |
| R3_PAPER_HEDGE — Paper con Hedge attivo | paper | F5-T1, F5-T2, F5-T3 |
| R4_GO_NO_GO — GO/NO-GO pack (paper month) | paper | F6-T2 |
| R5_LIVE_ENABLE — Live enable (sempre human-confirmed) | live | F6-T3 |

### Capital tiers (scope funzionale)
| Tier | Strategie | Target | Max posizioni |
|---|---|---:|---:|
| MICRO (€1.000–€2.000) | Vertical Spread, Bull Put (IWM) | 0.8–1.5%/mese | 1–2 |
| SMALL (€2.000–€5.000) | Iron Condor (IWM), Bull Put, Wheel | 1.2–2.5%/mese | 2–3 |
| MEDIUM (€5.000–€15.000) | Iron Condor (SPY/QQQ), PMCC, Calendar | 1.5–3.0%/mese | 3–5 |
| ADVANCED (€15.000+) | Multi-sottostante, Ratio Spread | 2.0–4.0%/mese | 4–8 |

### Tier Feature Matrix
> Il `capital_tier` (determinato dal capitale) definisce il tetto massimo disponibile. L'`active_mode` è la modalità operativa scelta dall'operatore (`active_mode ≤ capital_tier`).

#### Stack tecnico per tier
| Tier | Capitale | Milestone req. | XGBoost | HMM | Corr.Det. | Sizing | Kelly | TWAP/VWAP | Hedge |
|---|---|---|:---:|:---:|:---:|---|:---:|:---:|:---:|
| **MICRO** | €1.000–€2.000 | R2_PAPER_OPERATOR | ✅ | ❌ | ❌ | adaptive_fixed_fractional | ❌ | ❌ | ❌ |
| **SMALL** | €2.000–€5.000 | R2_PAPER_OPERATOR | ✅ | ⚠️ post-qual | ❌ | adaptive_fixed_fractional_to_kelly | ⚠️ N≥50 | ❌ | ❌ |
| **MEDIUM** | €5.000–€15.000 | R3_PAPER_HEDGE | ✅ | ✅ | ✅ | kelly_fractional | ✅ | ✅ | ✅ |
| **ADVANCED** | €15.000+ | R5_LIVE_ENABLE | ✅ | ✅ | ✅ | kelly_fractional | ✅ | ✅ | ✅ |

#### Strategie e UI per tier
| Tier | Strategie | Sottostanti | UI features |
|---|---|---|---|
| **MICRO** | Bull Put (IWM), Vertical Spread | IWM | single_opportunity, score_breakdown, confirm_reject_abort, risk_summary |
| **SMALL** | Iron Condor (IWM), Bull Put, Wheel (CSP→CC) | IWM, SPY | multi_opportunity_ranking, shap_breakdown, wheel_state_view, confirm_reject_modify_abort |
| **MEDIUM** | Iron Condor (SPY/QQQ), PMCC, Calendar | SPY, QQQ, IWM | multi_underlying_dashboard, hedge_status_panel, scenario_stress_view, full_transparency_protocol |
| **ADVANCED** | Multi-sottostante, Ratio Spread, + tutto MEDIUM | SPY, QQQ, IWM, multi | full_dashboard, multi_leg_visualizer, ratio_spread_builder, delta_overlay_panel, queue_position_awareness |

#### Gate di upgrade tier
| Tier → | Min trade | Sharpe OOS | Max DD | Kelly req. | Data mode |
|---|---:|---:|---:|:---:|---|
| **MICRO** | 50 | ≥0.6 | <15% | — | VENDOR_REAL_CHAIN |
| **SMALL** | 50 | ≥0.7 | <12% | ✅ | VENDOR_REAL_CHAIN |
| **MEDIUM** | 50 | ≥0.8 | <10% | ✅ | VENDOR_REAL_CHAIN |
| **ADVANCED** | — | — | — | — | — (tier finale) |

_Generato automaticamente; modificare `config/release_plan_go_nogo.json` e rieseguire `py tools/hf_release_plan_go_nogo.py`._
<!-- END GO_NOGO_RELEASE_PLAN -->
