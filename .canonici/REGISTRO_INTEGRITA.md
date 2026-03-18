# REGISTRO INTEGRITÃ€ â€” v.T.11.13

## Build 2026-03-18 — [bonifica-ROC30+ROC35] Tier naming + Wheel integration

| File | Tipo | Note |
|---|---|---|
| `.canonici/00_MASTER.md` | upd | Bonifica TOC: STARTER→OPERATIONAL → MICRO→SMALL→MEDIUM→ADVANCED; Piano 90gg → Roadmap R0-R5 |
| `docs/guide/07_tier_strategie.md` | new | Cap. 6 guida — Tier e strategie (MICRO/SMALL/MEDIUM/ADVANCED, Wheel, Iron Condor, router regime) |
| `docs/guide/trade_lifecycle.html` | upd | Slide 11-16: ciclo Wheel (IDLE/CSP/ASSIGNED/CC/CLOSED) + Tier Roadmap |
| `docs/guide/index.md` | upd | Prefazione: aggiunto riferimento capitolo Tier e strategie |
| `execution/wheel_storage.py` | new | DuckDB schema + CRUD per Wheel positions (init_wheel_schema, save, load, list) |
| `api/opz_api.py` | upd | Endpoint /opz/wheel/positions, /opz/wheel/new, /opz/wheel/transition; rimossa auth token (nginx basic auth) |
| `ui/src/App.tsx` | upd | Pannello Wheel in War Room tab (state machine badges, table CSP/CC/premium/cycles) |
| `ui/src/vite-env.d.ts` | new | Vite type declarations (ImportMeta.env) |
| `Dockerfile.nginx` | upd | Multi-stage: Node.js (React build) + Python/MkDocs + nginx:alpine |
| `docker/nginx.conf` | upd | Nginx gateway: basic auth, /guide/, /opz/ proxy, SPA routing |
| `docker-compose.yml` | upd | api + nginx services; NGINX_PASSWORD env; named volumes |

## Build 2026-03-05 10:14:26 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/paper_metrics.py` | `â€”` | `39186a28ce59â€¦` | new | F6-T1: paper telemetry metrics + gate evaluation (equity snapshots + trade journal). |
| `execution/storage.py` | `2249dd3cdfc5â€¦` | `cd5d4264b6e3â€¦` | upd | F6-T1: add paper tables (paper_equity_snapshots/paper_trades/compliance_events) to execution DB schema. |
| `api/opz_api.py` | `8abf8bea6ec7â€¦` | `148ab3bc95e1â€¦` | upd | F6-T1: FastAPI endpoints to log snapshots/trades + view paper summary/gates in Operator Console. |
| `ui/src/App.tsx` | `1a384ba1d854â€¦` | `79bd597419e1â€¦` | upd | F6-T1: Operator Console adds Paper metrics panel + logging controls (snapshots/trades). |
| `tools/f6_t1_paper_metrics.py` | `â€”` | `ca37f3446a56â€¦` | new | Tool: compute paper metrics + gates (PASS/FAIL) for F6-T1 and GO/NO-GO. |
| `tests/test_f6_t1_paper_metrics.py` | `â€”` | `7086ca8b194aâ€¦` | new | Unit tests: deterministic synthetic paper metrics => gates PASS/FAIL behavior. |
| `.qoaistate.json` | `235536a61044â€¦` | `8832129e9cc1â€¦` | upd | Advance progress: mark F6-T1 complete; set next_step=F5-T1; add note. |
| `.step_index.json` | `848f754e72f5â€¦` | `60c032b8e8ecâ€¦` | upd | Reconciled step index from updated state (certify_steps drift-free). |
| `.canonici/MANIFEST.txt` | `d480fadb548aâ€¦` | `REBUILT` | upd | Update hashes + build timestamp refresh after F6-T1 patch. |

## Build 2026-02-26 19:55:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/order_reducer.py` | `â€”` | `8d15b6311399â€¦` | new | D2.15: deterministic reducer + invariants (pure; no I/O). |
| `tests/test_d2_15_state_machine.py` | `â€”` | `abc850553654â€¦` | new | D2.15 unit tests: determinism, illegal transitions, broker-unavailable dominance, filled invariant. |
| `.qoaistate.json` | `021e30f1e582â€¦` | `f6741f98fc89â€¦` | upd | Advance progress: add D2.15 step; set next_step=D2.16. |
| `.canonici/MANIFEST.txt` | `594a14f56d0eâ€¦` | `3b7c97aaf3bcâ€¦` | upd | Update hashes + build timestamp refresh. |

## Build 2026-02-26 15:30:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `strategy/__init__.py` | `â€”` | `a654a3633cd9â€¦` | new | Phase 4 additive package scaffold (no Gate0 impact). |
| `strategy/scoring.py` | `a2bebf92f32aâ€¦` | `3532cb33da12â€¦` | new | F4: score 4 pilastri + hard filters + kelly_fractional v11.1. |
| `tests/test_f4_scoring_kelly.py` | `â€”` | `75c4926f8fdaâ€¦` | new | Unit tests for F4-T1 (scoring) and F4-T2 (kelly). |
| `.qoaistate.json` | `bff88c05fce2â€¦` | `6d8d9d882b1fâ€¦` | upd | Advance progress: add F4.1 step + set next_step=F4.3. |
## Build 2026-02-26 14:10:00 UTC
| `.canonici/MANIFEST.txt` | `7f8dfb66fa12â€¦` | `62c8a5a3f8aaâ€¦` | upd | Update hashes + include Phase 4 files; build timestamp refresh. |
| `.canonici/REGISTRO_INTEGRITA.md` | `e30f1161b433â€¦` | `7ad86f402f85â€¦` | upd | Add build entry for F4.1 and updated manifest hashes. |

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/ack.py` | `n/a` | `f4c7d3d9bf2bâ€¦` | add | Add AckStatus.BROKER_UNAVAILABLE enum member for paper/live taxonomy compatibility. |
| `execution/ack_taxonomy.py` | `7805224cd9a0â€¦` | `0d66906f028eâ€¦` | upd | Broker-unavailable dominance heuristic; keep ACK/timeout semantics unchanged; accept ack_deadline_ts_utc kw. |
| `.qoaistate.json` | `195c4623d1baâ€¦` | `9a534a3598f2â€¦` | upd | Record normalization hotfix metadata (D2.NORM.1). |
| `.canonici/MANIFEST.txt` | `n/a` | `7c18fe6b36a6â€¦` | upd | Refresh hashes/sizes after BROKER_UNAVAILABLE normalization. |
| `REGISTRO_INTEGRITA.md` | `f2affb11a6b0â€¦` | `60d2b25f35b9â€¦` | upd | Update integrity register. |


## Build 2026-02-26 12:00:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/ack_taxonomy.py` | `n/a` | `2e33e2b180b6â€¦` | add | Add compatibility module for InternalEvent ACK taxonomy; no behavior change to existing classify_ack. |
| `.qoaistate.json` | `8da2b007bf99â€¦` | `bda12c10f88dâ€¦` | upd | Record normalization patch metadata (D2.NORM). |
| `.canonici/MANIFEST.txt` | `cc9b4e13deeeâ€¦` | `29ef6b67b9cfâ€¦` | upd | Normalize manifest paths (dot baseline dir) + add ack_taxonomy and .qoaistate entries; refresh build timestamp. |
| `REGISTRO_INTEGRITA.md` | `10d8cf4d6b05â€¦` | `3b4d5be56aaaâ€¦` | upd | Update integrity register. |

## Build 2026-02-24 18:25:32 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `validator.py` | `b40d82396edfâ€¦` | `eae499bc0032â€¦` | upd | Add env/deps preflight (P0-A4) + dev skips ib_insync checks. |
| `03_SETUP.md` | `1048bc522bafâ€¦` | `ed6b62df92c2â€¦` | upd | Add PowerShell install commands (core/broker/dev). |
| `PATCH_NOTES.md` | `0a15d660bf81â€¦` | `6599f924c094â€¦` | upd | Document Fase 1 patch. |
| `MANIFEST.txt` | `6751aa978ab0â€¦` | `a96b48323164â€¦` | upd | Update hashes + include new requirements files (excludes MANIFEST/REGISTRO to avoid circular hash). |
| `REGISTRO_INTEGRITA.md` | `146f6bdeb8d7â€¦` | `4d7146ecc5d3â€¦` | upd | Update registry for this build. |
| `requirements-core.txt` | `â€”` | `2f960fb06fa4â€¦` | new | New requirements set. |
| `requirements-broker-ib.txt` | `â€”` | `594faf34407câ€¦` | new | New requirements set. |
| `requirements-dev.txt` | `â€”` | `2af92fc67cc2â€¦` | new | New requirements set. |

## Snapshot v.T.11.2 (legacy section-hash tables)


## File: `00_MASTER.md`

| Sezione | Righe | SHA_prev | SHA_curr | Stato | Note |
|---|---:|---|---|:---:|---|
| Governance della suite canonica (5 file) | 6 | â€” | ed320105d140 | NEW | Nuova sezione governance suite 5-file + regola integritÃ . |
| Regola di integritÃ  | 4 | â€” | bd464612115e | upd | Sezione nuova/aggiornata (motivazione qui). |
| Appendici operative | 3 | 77157cd97d8c | 77157cd97d8c | 0 | â€” |

## File: `01_TECNICO.md`

| Sezione | Righe | SHA_prev | SHA_curr | Stato | Note |
|---|---:|---|---|:---:|---|
| T7.1bis â€” Relazioni & Vincoli (ERD logico) | 133 | 6b3207f579fc | 6b3207f579fc | 0 | â€” |

## File: `02_TEST.md`

| Sezione | Righe | SHA_prev | SHA_curr | Stato | Note |
|---|---:|---|---|:---:|---|
| 1) Strategia Test | 3 | â€” | 3a53e24a63e2 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Principi | 4 | â€” | 9553956499d2 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Ambienti e dataset | 0 | â€” | 01ba4719c80b | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| DEV (mockup/studio) | 3 | â€” | 5c51374b7c0f | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| STAGING (paper) | 2 | â€” | c32e3197eda3 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| PROD (live) | 1 | â€” | 98261be23d43 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Gates | 5 | â€” | e550182f534c | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| 2) Test Suite (vK.11.2) | 322 | â€” | 11320025ae79 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| 3) Traceability Matrix | 11 | â€” | 664ce2e51090 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |

## File: `03_SETUP.md`

| Sezione | Righe | SHA_prev | SHA_curr | Stato | Note |
|---|---:|---|---|:---:|---|
| 1) TODO Phase 0 (fonte normativa) | 3 | â€” | f56bdba528df | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Convenzioni | 3 | â€” | e00e2d7e76f9 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| A) Base (comune) | 4 | â€” | 4e9148806958 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| B) Storage / DuckDB | 3 | â€” | d2eaaebae7c2 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| C) Dataset sintetico (mockup) | 2 | â€” | 6339f82d1df7 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| D) Broker / Market Data (paper) | 2 | â€” | a350da55972a | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| E) Ops / Sicurezza | 2 | â€” | 201ba04c60d1 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| GO/NO-GO Phase 0 | 2 | â€” | 33bb498dfff0 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| 2) Validator automation (spec) | 3 | â€” | fb8996cccf44 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Input | 2 | â€” | 245e624d305b | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Output | 3 | â€” | d66d8bc939f8 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Regole | 2 | â€” | f108121c9b0b | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Contract JSON (minimo) | 12 | â€” | bc54b86810e4 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| 3) DuckDB + Dati sintetici + Lineage (obbligatori) | 4 | â€” | 43081427118f | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |
| Lineage fields minimi | 7 | â€” | 2153b77f9963 | NEW | Documento nuovo canonico: contenuti integrati da TestPlan v11.2. |

## File: `04_APPENDICI.md`

| Sezione | Righe | SHA_prev | SHA_curr | Stato | Note |
|---|---:|---|---|:---:|---|
| Appendice A â€” Walkthrough Operativo | 0 | â€” | 01ba4719c80b | upd | Aggregazione appendici baseline in un unico file (nessuna perdita intenzionale). |
| Timeline (CET) | 6 | a046474bb35e | a046474bb35e | 0 | Contenuto invariato (spostato/ri-contestualizzato). |
| Numeri esempio | 3 | 8af0edf7b988 | 8af0edf7b988 | 0 | Contenuto invariato (spostato/ri-contestualizzato). |
| Appendice B â€” Moduli Avanzati (Non Canonici) | 0 | â€” | 01ba4719c80b | upd | Aggregazione appendici baseline in un unico file (nessuna perdita intenzionale). |
| Lockout (obbligatorio) | 5 | 8030aa3ff011 | 8030aa3ff011 | 0 | Contenuto invariato (spostato/ri-contestualizzato). |
| Scopo | 1 | 7c6ea78f3d4d | 7c6ea78f3d4d | 0 | Contenuto invariato (spostato/ri-contestualizzato). |
| Nota | 1 | 9029f595d1cf | 9029f595d1cf | 0 | Contenuto invariato (spostato/ri-contestualizzato). |
| Stato integrazioni memo (baseline) | 0 | â€” | 01ba4719c80b | upd | Aggregazione appendici baseline in un unico file (nessuna perdita intenzionale). |

## Registro aggiornamento â€” v.T.11.3.1
Build: 2026-02-24 13:14:39 UTC
Modifiche minime:
- Fix Kelly lower bound in `01_TECNICO.md`: confronto diretto su `f` (`if f < min_trade_pct/100`), eliminata forma ambigua con `capital`.
- Aggiornamento `02_TEST.md` (nota hotfix) e rigenerazione `MANIFEST.txt`.

## Registro aggiornamento â€” v.T.11.3.2
Build: 2026-02-24 12:04:17 UTC
Modifiche minime:
- Inserite nuove righe nella Traceability Matrix di 02_TEST.md per i test hardening e cross-fase.
- Rigenerato MANIFEST e aggiornato registro.

## Registro aggiornamento â€” v.T.11.4
Build: 2026-02-24 12:14:38 UTC
Modifiche minime (base: v.T.11.3.2 FULL):
- Policy pricing operativo: **SVI obbligatorio**; Heston solo stress/scenario.
- Gate Kelly: abilitazione solo con `DATA_MODE=VENDOR_REAL_CHAIN` e `N_closed_trades>=50`.
- Hedge policy scenario-based (Base/Shock) con vincolo su loss Shock.
- Introduzione metrica `MarginEfficiency` (Return annualizzato / Avg_Margin_Used).
- Aggiunta percorso **STARTER-LITE** (checklist 8 item).
- Aggiornati `02_TEST.md` (nuovi gate + traceability), bump header su docs, rigenerato `MANIFEST.txt`.

## Registro aggiornamento â€” v.T.11.4.1
Build: 2026-02-24 12:20:14 UTC
Modifiche minime (base: v.T.11.4 FULL):
- Allineato MASTER al TECNICO su HMM early-warning: rimosso claim â€œ1â€“2 giorni primaâ€ non garantito; introdotta policy claim + dipendenza da F2-T_HMM_event_OOS.
- Quantificato budget runtime VaR/CVaR: **â‰¤ 5s** per **â‰¤10 posizioni** e **10.000 scenari** (PERF_VaR_runtime_budget).
- Tiering execution: STARTER-LITE usa esecuzione semplificata (ordine singolo/ladder); TWAP/VWAP riservati a OPERATIONAL; nota su limiti IBKR paper.
- Aggiornati header docs, rigenerato MANIFEST e aggiornato registro.

## Registro aggiornamento â€” v.T.11.7
Build: 2026-02-24 12:39:01 UTC
Modifiche minime (base: v.T.11.4.1 FULL):
- Validator automation: policy exit codes (0/2/10) + hard stop CRITICAL; WARNING non bloccanti (con test dedicati).
- **Kelly Lite Bridge rimosso**; adottato **Adaptive Fixed Fractional** pre-50 trade (regime-based, NO false precision).
- HMM: introdotto gate di **qualification non-VIX** su 3 famiglie shock (ensemble upgrade solo se qualificato); default monitoring-only.
- Introdotto **Correlation Regime Detector** (SPYâ€“TLT) con flag `CORRELATION_BREAKDOWN` e azione su sizing/nuove posizioni.
- Aggiornati 00_MASTER, 01_TECNICO, 02_TEST, 04_APPENDICI, bump header 03_SETUP; rigenerato MANIFEST e aggiornato registro.

## Registro aggiornamento â€” v.T.11.8
Build: 2026-02-24 12:55:46 UTC
Modifica chirurgica (base: v.T.11.7 FULL):
- Aggiunta sezione "Natura del Ranking Score" nel MASTER per chiarire che il punteggio misura qualitÃ  dellâ€™opportunitÃ  e non probabilitÃ  di successo o previsione di P&L.
- Nessuna modifica a logica, gate o perimetro file.
- Rigenerato MANIFEST e aggiornato registro.

## Registro aggiornamento â€” v.T.11.9
Build: 2026-02-24 12:57:38 UTC
Modifica chirurgica (base: v.T.11.8 FULL):
- Aggiunta sezione "Automation Boundary Protocol" nel MASTER.
- Nessuna modifica a logica di gate, sizing o perimetro file.
- Rigenerato MANIFEST e aggiornato registro.


## Registro aggiornamento â€” v.T.11.10
Build: 2026-02-24 13:00:03 UTC
Correzioni residue (base: v.T.11.9 FULL):
1. Inserito riferimento esplicito a STARTER-LITE nel Â§7 STARTER del MASTER.
2. Specificato metodo di stima scenari hedge: applicazione scenari VIX storici T5.3 al P&L corrente.
3. Normalizzata intestazione Appendici a versione coerente v.T.11.10.
- Rigenerato MANIFEST e aggiornato registro.



## Registro aggiornamento â€” v.T.11.11
Build: 2026-02-24 13:04:20 UTC
Correzioni di coerenza (base: v.T.11.10 FULL):
1. Allineamento TWAP STARTER-LITE in Appendici con riferimento esplicito al MASTER.
2. Aggiunta Degradation Policy esplicita per Performance Budget VaR.
3. Esplicitato divieto formale di Kelly â€œbridgeâ€ o metriche brevi (Sharpe 30g).
- Rigenerato MANIFEST e aggiornato registro.

## Registro aggiornamento â€” v.T.11.12
Build: 2026-02-24 13:14:39 UTC
Correzioni residue (base: v.T.11.11 FULL):
1. MASTER: aggiunto riferimento esplicito STARTER-LITE nel Â§7 (direzione normativa MASTER â†’ Appendici).
2. APPENDICI: aggiunto metodo di stima scenari hedge (scenari VIX T5.3 applicati al P&L corrente via historical shock replay).
3. APPENDICI: chiarita gerarchia documentale (MASTER normativo, Appendici implementative).
- Aggiornati header versione/build e rigenerato MANIFEST.

## Registro aggiornamento â€” v.T.11.12.1
Build: 2026-02-24 13:19:52 UTC
Rafforzamenti puntigliosi (base: v.T.11.12 FULL):
1) Unificati header versione/build (rimossi riferimenti incoerenti v.T.11.3 nei front-matter).
2) Stack DB in TECNICO T9: esplicitato DuckDB come primario DEV (Postgres prod se previsto).
3) Chiarito sizing in DEV sintetico: `0.0` per evitare interpretazioni economiche; ammesso sizing virtuale solo per engineering test.
4) Diagramma MASTER: TWAP/VWAP marcato **[OPERATIONAL only]**.
5) Allineato acceptance HMM (F2-T2) alla qualification event/family-based (â‰¥2/3 famiglie) coerente con gate formale.
6) Rimosso riferimento a file inesistente `02_AUTOMATION_VALIDATOR_SPEC.md` (spec incorporata in Appendici).
7) Hedge: resa policy scenario-based riferimento primario; degradato esempio 20% credito a puro didattico con avviso esplicito + metodo T5.3.
- Rigenerato MANIFEST e aggiornato REGISTRO.


## Registro aggiornamento â€” v.T.11.13
Build: 2026-02-24 15:27:41 UTC
Release implementativa (base: v.T.11.12.2 FULL):
- Implementato Gate 0 / Phase 0 Validator: `validator.py` + `scripts/validate_phase0.ps1`.
- Phase 0 include broker connectivity (policy: dev=WARNING; paper/live=CRITICAL) + smoke test option bid/ask (paper/live=CRITICAL).
- Aggiunto init minimale DuckDB: `scripts/init_db.py` + marker `db/schema_applied.ok`.
- Aggiunti template `config/*.toml` e `requirements.lock` placeholder.
- Aggiornati SETUP/APPENDICI/TEST con spec Gate 0 (checklist, output, exit codes).
- Rigenerato MANIFEST.

---
## Addendum â€” v.T.11.13 (Dev folders scaffold)

Stato: `upd` (estensione per rendere operativa Phase 0 su filesystem pulito).

### NEW â€” Cartelle runtime richieste (Phase 0)
- `db/` (placeholder: `.gitkeep`)
- `data/` (placeholder: `.gitkeep`)
- `logs/` (placeholder: `.gitkeep`)
- `reports/` (placeholder: `.gitkeep`)

### NEW â€” Documentazione Control Framework
- `docs/QOAI_MASTER_CONTROL_FRAMEWORK_v1.2.md`

Nota: queste aggiunte completano i prerequisiti `P0-A1` (required dirs) del validator.



## Build 2026-02-24 19:45:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `validator.py` | `eae499bc0032â€¦` | `5cd2f5984931â€¦` | upd | Report metadata (`generated_at_utc`, `execution_mode`, etc.) + report hygiene (`severity_on_fail`, `severity_effective`). |
| `docs/TRACEABILITY_PHASE0.md` | `n/a` | `4515562b92faâ€¦` | add | Phase0 â†” Framework v1.2 mapping (traceability). |
| `PATCH_NOTES.md` | `6599f924c094â€¦` | `6c9a5717fd48â€¦` | upd | Add Fase 1.4 notes (traceability + report hygiene). |
| `REGISTRO_INTEGRITA.md` | `4d7146ecc5d3â€¦` | `562765a3bf9dâ€¦` | upd | Update integrity register. |

---
## Build 2026-02-26 13:30:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/ack_taxonomy.py` | `2e33e2b180b6â€¦` | `7805224cd9a0â€¦` | upd | Compat: accetta `ack_deadline_ts_utc` (deadline assoluta) + mantiene `ack_deadline_s` (relativa). |
| `.qoaistate.json` | `bda12c10f88dâ€¦` | `195c4623d1baâ€¦` | upd | Registro stato patch normalization hotfix (D2.NORM). |
| `.canonici/REGISTRO_INTEGRITA.md` | `a9f9d3820922â€¦` | `f2affb11a6b0â€¦` | upd | Aggiunta entry hotfix D2.13 (keyword arg). |
| `.canonici/MANIFEST.txt` | `bd8c25da835dâ€¦` | `271bf8679f1câ€¦` | upd | Rigenerato manifest (hash+size) post-hotfix. |


---
## Build 2026-02-26 16:45:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `strategy/scoring.py` | `a2bebf92f32aâ€¦` | `3532cb33da12â€¦` | upd | Hotfix: guard Kelly lower-bound per low-RR (b<=1.10) per caso NO_TRADE in F4. |
| `.qoaistate.json` | `bff88c05fce2â€¦` | `6d8d9d882b1fâ€¦` | upd | Registro stato hotfix F4.1.HF1 + last_validation (0/0/10). |
| `.canonici/REGISTRO_INTEGRITA.md` | `e30f1161b433â€¦` | `` | upd | Aggiunta entry build hotfix F4.1.HF1. |
| `.canonici/MANIFEST.txt` | `7f8dfb66fa12â€¦` | `` | upd | Rigenerato manifest (hash+size) post-hotfix F4.1.HF1. |

## Build 2026-02-26 20:45:00 UTC

| File | SHA_prev | SHA_curr | Stato | Note |
|---|---|---|:---:|---|
| `execution/state_machine.py` | `â€”` | `1aa34e690cf3â€¦` | mod | D2.16: accept ACKED state to match journal transitions. |
| `execution/journal_state.py` | `â€”` | `ac223c142e6aâ€¦` | new | D2.16: derive state from journal events via D2.15 reducer (opt-in). |
| `tests/test_d2_16_journal_state_integration.py` | `â€”` | `edb68d7ff941â€¦` | new | D2.16 unit test: derived ACKED state matches journal. |
| `.qoaistate.json` | `6d8d9d882b1fâ€¦` | `1eb3350cc151â€¦` | mod | Timeline update: close D2.16; next_step D2.17; last_validation 0/0/10. |
| `.canonici/MANIFEST.txt` | `` | `4a531b3767daâ€¦` | mod | Manifest refresh for D2.16 build. |
| `.canonici/REGISTRO_INTEGRITA.md` | `` | `4d58df8426e8â€¦` | mod | Registro entry for D2.16 build. |

---

## [bonifica-ROC30] 2026-03-17 — Unificazione nomenclatura tier MICRO/SMALL/MEDIUM/ADVANCED

| File | Modifica |
|------|----------|
| `.canonici/00_MASTER.md` | Bonifica §7 (tabella 4-tier), §8 (roadmap milestones), addendum STARTER-LITE→MICRO, Execution Policy, sizing progression, refs appendici |
| `.canonici/04_APPENDICI.md` | Rename STARTER-LITE→MICRO nelle sezioni manuali; rigenera blocco auto |
| `config/release_plan_go_nogo.json` | Aggiunta `tier_feature_matrix` (v2): prerequisite milestone, ML stack, sizing, UI features, upgrade gate per tier |
| `tools/hf_release_plan_go_nogo.py` | Esteso renderer: tabelle Stack tecnico, Strategie/UI, Gate upgrade |
