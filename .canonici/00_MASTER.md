# QuantOptionAI â€” MASTER (Canon)

_Versione: v.T.11.13



---



## Governance della suite canonica (5 file)



- `00_MASTER.md` (questo): contratto e regole di alto livello

- `01_TECNICO.md`: specifiche implementative (DB, modelli, risk, execution)

- `02_TEST.md`: strategia + suite test + gates + traceability

- `03_SETUP.md`: Phase 0 (bootstrap/validate/certify) + DuckDB + dati sintetici

- `04_APPENDICI.md`: walkthrough + moduli avanzati + note operative



### Regola di integritÃ 



## Data Provenance & Execution-Grade Policy (v.T.11.3)



Il sistema opera in due modalitÃ  formalmente distinte (obbligatorio log):



- `DATA_MODE = SYNTHETIC_SURFACE_CALIBRATED`

- `DATA_MODE = VENDOR_REAL_CHAIN`



### 1) SYNTHETIC_SURFACE_CALIBRATED (DEV / engineering validation)

- Underlying: dati reali storici (SPY/IWM/VIX, ecc.)

- Superficie IV: **sintetica calibrata** su proxy (es. VIX level, percentile regime, skew parametrico)

- Catena opzioni: derivata deterministicamente dalla superficie IV



**Policy**:

- **NON execution-grade** (risultati economici non interpretabili come edge reale)

- **Kelly disabilitato** (vedi Â§ sotto)

- Report obbligatorio watermark:

  - `DATA_MODE: SYNTHETIC_SURFACE_CALIBRATED`

  - `NOT EXECUTION GRADE`



### 2) VENDOR_REAL_CHAIN (STAGING/PROD / execution-grade)

Richiede dati storici strike-level con: IV per strike, OI, greche coerenti, bid/ask storici.



Solo in questa modalitÃ  sono ammessi:

- interpretazione economica dei KPI

- calibrazione sizing avanzato (Kelly)

- validazione edge su orizzonte lungo



### Kelly sizing constraint

Se `DATA_MODE == SYNTHETIC_SURFACE_CALIBRATED` allora `Kelly_enabled = False` (hard fail se forzato).



### Integrity rule (run-level)

Ogni run/backtest deve loggare: `DATA_MODE`, `data_source`, (se sintetico) parametri superficie, (se vendor) nome vendor.







Questa versione include `REGISTRO_INTEGRITA.md` nello ZIP: ogni variazione Ã¨ tracciata e motivata.

---

## Addendum v.T.11.14 — Operational Layer (Scheduler + Briefing + Control Plane)

### Session Scheduler

Il sistema esegue automaticamente due sessioni giornaliere (configurabili via `config/paper.toml` sezione `[sessions]`):

| Sessione | Orario default | Scopo |
|---|---|---|
| `morning` | 09:00 CET | Scan universo, regime check, briefing |
| `eod` | 16:30 CET | Snapshot equity, log chiusura |

- Le sessioni sono eseguite come subprocess asincrono (non bloccano l'API)
- Trigger: `auto` (scheduler) o `manual` (operatore via `POST /opz/session/run`)
- Ogni sessione produce una riga in `session_logs` (DuckDB) — vedi `01_TECNICO.md` T7.4
- Stato scheduler: `GET /opz/session/status` → `{enabled, running, last_morning, last_eod, next_morning, next_eod}`

### Briefing Audio (NARRATORE)

Il sistema genera un bollettino audio giornaliero (MP3 via edge-tts):

- Generazione: `POST /opz/briefing/generate` (avvia in background)
- Lista briefing: `GET /opz/briefing/list` (ultimi 20)
- Play: `GET /opz/briefing/latest` (MP3 stream)
- Anteprima testo: `GET /opz/briefing/text`
- Il briefing viene inviato anche via Telegram (se observer attivo)
- **Prerequisito**: `edge-tts` installato nell'ambiente

### Control Plane (IBWR + Observer Telegram)

**IBWR** — controllo connessione broker IBKR:

- `POST /opz/ibwr/service` con `{"action": "start"|"stop"|"status"}`
- `stop` blocca nuovi ordini (equivalente soft kill switch); probe su porte 4001/4002

**Observer Telegram** — canale di notifica:

- `POST /opz/execution/observer` con `{"action": "on"|"off"}`
- `on`: notifiche attive (regime change, briefing, errori sessione)
- `off`: silenzio totale (consigliato in manutenzione)
- Kill switch forza observer OFF automaticamente

### Flusso Operational Layer

```
[Session Scheduler] --> morning/eod subprocess (session_runner.py)
        |
        v
   regime check --> universe scan --> briefing generate
        |
        v
[session_logs DuckDB] <-- log riga per sessione
        |
        v
[Briefing MP3] --> NARRATORE (UI player) + Telegram (se observer ON)

[IBWR Control] --> porte 4001/4002 --> IBKR connection on/off
[Observer]     --> Telegram bot --> notifiche operative
```

### Contratti di errore (Operational Layer)

I contratti normativi di comportamento su errore sono definiti in `04_APPENDICI.md` — Appendice E.

Invarianti non negoziabili (estratto):
- Nessun componente critico deve crashare l'API — ogni eccezione va catturata e restituita come errore HTTP strutturato
- Kill switch ha priorità assoluta su qualsiasi altro meccanismo (incluso IBWR)
- Ogni sessione deve produrre una riga in `session_logs`, anche in caso di errore parziale
- Watermark `DATA_MODE` obbligatorio su ogni report — assenza = CRITICAL FAIL nel validator
- Kelly disabilitato se `DATA_MODE != VENDOR_REAL_CHAIN` OR `N_closed_trades < 50` — violazione = run non certificabile

---



# QuantOption AI v11.1 â€” MASTER (Canonico)



QUANTOPTION AI v11.1 UNIFIED

Master Document + Technical Appendix

DOCUMENTO MASTER â€” QuantOption AI v11.1

Versione: v.T.11.13

Data: 2026-02-24

Destinatario: Trader retail, implementatori, quantitative analyst

Stato: Aggiornato con miglioramenti chirurgici v11.1

INDICE MASTER

Visione e Filosofia del Sistema

Architettura Generale: 3 Moduli Core

Modulo 1: Market Regime Detection (Aggiornato v11.1)

Modulo 2: Trade Selection & Scoring (Aggiornato v11.1)

Modulo 3: Risk Management & Execution (Aggiornato v11.1)

Strategie Certificate: Parametri Ottimizzati

Tier Progressione: MICRO → SMALL → MEDIUM → ADVANCED

Roadmap Implementazione (milestone R0–R5)

Metriche di Successo e Kill Switch

1. VISIONE E FILOSOFIA

QuantOption AI Ã¨ un sistema quantitativo per il trading di opzioni su azioni e ETF, progettato per trader retail che vogliono approcciarsi al income trading con rigore metodologico istituzionale.

Principi Non Negoziabili:

Edge misurabile: Ogni trade deve avere un vantaggio statistico quantificato (IVR, skew, term structure)

Sopravvivenza prima del profitto: Max drawdown <15% in ogni scenario storico stress

Anti-overfitting: Walk-Forward Analysis (WFA) obbligatoria su ogni parametro

Human-in-the-loop: Il sistema suggerisce, l'operatore decide (kill switch psicologico)

Target Realistico v11.1: 0.8â€“2.5% mensile netto su capitale impegnato (10â€“25% annuo), Sharpe ratio 0.8â€“1.2, max drawdown <15%.

2. ARCHITETTURA GENERALE

```

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚                    MARKET DATA LAYER                        â”‚

â”‚    yfinance + CBOE VIX + FRED + ORATS Free (5 ticker)      â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

                              â†“

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚              FEATURE ENGINEERING (15 Core)                  â”‚

â”‚    VolatilitÃ  (5) | Options Chain (5) | Macro Regime (5)   â”‚

â”‚    + Microstructure (3) [v11.1]                            â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

                              â†“

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚              REGIME CLASSIFICATION v11.1                    â”‚

â”‚    Primary: XGBoost (3 classi)                             â”‚

â”‚    Ensemble: HMM Secondary [v11.1]                         â”‚

â”‚    Output: NORMAL (0) | CAUTION (1) | SHOCK (2)            â”‚

â”‚    + Regime Transition Probability [v11.1]                 â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

                              â†“

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚           OPPORTUNITY SCORER (4 Pilastri)                   â”‚

â”‚    35% Vol Edge | 25% LiquiditÃ  | 25% R/R | 15% Regime     â”‚

â”‚    + Kelly Fractional con Lower Bound [v11.1]              â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

                              â†“

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚              RISK MANAGEMENT LAYER                          â”‚

â”‚    Position Sizing (Kelly 25% max)                         â”‚

â”‚    3-Layer Drawdown Control                                â”‚

â”‚    VaR/CVaR Full Repricing                                 â”‚

â”‚    Tail Hedge (Put Spread mensile)                         â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

                              â†“

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”

â”‚              EXECUTION ENGINE v11.1                         â”‚

â”‚    Smart Limit Order Protocol                              â”‚

â”‚    + TWAP/VWAP for Wide Spreads [MEDIUM/ADVANCED only] [v11.1]                    â”‚

â”‚    + Queue Position Awareness [v11.1]                      â”‚

â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

```

3. MODULO 1: MARKET REGIME DETECTION (Aggiornato v11.1)

3.1 Classificazione Regime â€” Approccio Ensemble v11.1

Primary Model: XGBoost Classifier

Target: 3 classi basate su VIX media(t+1, t+5) vs percentili rolling 252g

Feature selection: Top 10 per SHAP importance

Calibrazione: Platt Scaling con 5-fold Purged CV

Training: Mensile con WFA rolling

Secondary Model: Hidden Markov Model (HMM) [v11.1]

Stati nascosti: 3 (Low Vol, Medium Vol, High Vol)

Osservabili: VIX, VIX3M, IV Rank, Credit Spread

Vantaggio: puÃ² fornire segnali anticipatori in specifici contesti (validati via test OOS event-based)

Integrazione: Se HMM prob(Shock) > 0.7 e XGBoost = CAUTION â†’ upgrade a SHOCK

Regime Transition Probability [v11.1]

Calcolo: Matrice di transizione 3x3 su rolling window 63g

Alert precoce: Se P(CAUTIONâ†’SHOCK) > 0.4 in 48h â†’ riduzione sizing 50%

3.2 Feature Regime (Top 10 + 3 Microstructure v11.1)



Rank	Feature	Importanza	Note v11.1

1	VIX/VIX3M Ratio	â˜…â˜…â˜…â˜…â˜…	Leading indicator

2	VIX Z-score (252g)	â˜…â˜…â˜…â˜…â˜…	Mean reversion

3	IV Rank SPY	â˜…â˜…â˜…â˜…â˜†	Edge primario

4	VIX Term Structure	â˜…â˜…â˜…â˜…â˜†	Contango/backwardation

5	SPY 10g Return	â˜…â˜…â˜…â˜†â˜†	Momentum

6	PCR Volume 5d MA	â˜…â˜…â˜…â˜†â˜†	Sentiment

7	Credit Spread HY-IG	â˜…â˜…â˜…â˜†â˜†	Risk-off leading

8	GEX Normalized	â˜…â˜…â˜†â˜†â˜†	Market maker positioning

9	GARCH Forecast Ratio	â˜…â˜…â˜†â˜†â˜†	Realized vs implied

10	Days to FOMC	â˜…â˜…â˜†â˜†â˜†	Event risk

11	Volume Profile Delta [v11.1]	â˜…â˜…â˜…â˜†â˜†	Order flow imbalance

12	OI Change Velocity [v11.1]	â˜…â˜…â˜†â˜†â˜†	Institutional activity

13	IV Curvature Accel [v11.1]	â˜…â˜…â˜…â˜†â˜†	Skew acceleration

3.3 Definizione Regime e Azioni



Regime	Condizione	Azione Sistema	Sizing

NORMAL	VIX < 20, term structure contango	Tutte le strategie abilitate	100%

CAUTION	VIX 20-28 o backwardation leggera	Spread stretti, filtro direzionale	50%

SHOCK	VIX > 28 o HMM P(Shock)>0.7	STOP nuovi trade, hedge attivo	0%

4. MODULO 2: TRADE SELECTION & SCORING (Aggiornato v11.1)

4.1 Filtri Hard (Eliminazione Automatica)



Filtro	Soglia	Motivo

Bid-ask spread	> 10% mid	Slippage eccessivo

Open Interest	< 100 contratti	LiquiditÃ  insufficiente

DTE	< 14 o > 60	Gamma risk / theta lento

Earnings proximity	< 7 giorni	Evento binario

IVR minimo	< 20 (short vol)	Edge statistico nullo

Margine	> 30% capitale	Position sizing eccessiva

TCC check	Credit < 3Ã—TCC	Trade matematicamente unprofitable

4.2 Score Composito â€” 4 Pilastri



Componente	Peso WFA	Range	Fonte

Vol Edge (IVR/IVP)	35%	28-42%	yfinance/ORATS

LiquiditÃ  (spread, OI, volume)	25%	20-30%	Options chain

Risk/Reward struttura	25%	20-30%	Strike selection

Regime Alignment	15%	10-20%	Regime classifier

Soglie:

Score â‰¥ 60: Presentazione operatore

Score â‰¥ 75: High Conviction (sizing 1.25Ã— in NORMAL)

4.3 Kelly Criterion Fractional [v11.1]

Formula Base:

```

f* = (p Ã— b - q) / b

dove: p = win rate, q = 1-p, b = avg win / avg loss

Correzioni v11.1:

Half-Kelly default: f = 0.5 Ã— f* (protezione da overestimation)

Lower bound dinamico: Se f < 0.5% del capitale â†’ NO TRADE (evita overtrading)

Upper bound hard: f_max = 25% capitale per posizione

Skewness adjustment: Se skewness P&L storico < -1.0 â†’ riduci f del 20%

Esempio Capitale â‚¬10,000:

Kelly calcolato: 1.2% â†’ Posizione â‚¬120 (OK)

Kelly calcolato: 0.3% â†’ NO TRADE (sotto lower bound)

```

5. MODULO 3: RISK MANAGEMENT & EXECUTION (Aggiornato v11.1)

5.1 VaR/CVaR Full Repricing

Metodologia: Monte Carlo con full repricing Heston/BSM (no delta-normal)



Metrica	Orizzonte	Soglia	Azione se Superata

VaR 99%	5 giorni	3% capitale	Alert

CVaR 99%	5 giorni	5% capitale	Riduzione sizing 50%

Stress Test	Storico	15% drawdown	Hedge attivazione

5.2 3-Layer Drawdown Control



Livello	Drawdown	Azione

Giallo	10%	Riduzione sizing 50%, hedge review

Arancione	15%	STOP nuove posizioni, hedge attivo

Rosso	20%	Kill switch, chiusura totale

5.3 Execution Protocol v11.1

Smart Limit Order Ladder:



Step	Prezzo	Timeout	Fallback	Condizione

1	Mid	2 min	Step 2	Spread < 10%

2	Mid - 1 tick	2 min	Step 3	â€”

3	Mid - 3 tick	2 min	Step 4	â€”

4	Mid - 5 tick	2 min	Step 5	Max slippage

5	Abbandono	â€”	Rivaluta domani	Edge eroso

TWAP/VWAP per Spread Ampio [v11.1]:

Se spread > $0.50 su Iron Condor 4-gambe â†’ attiva TWAP 15 min

Suddivisione ordine in 3 slice eseguite ogni 5 min

Queue position awareness: Se L2 data disponibile, piazza solo se posizione coda < 5

Regole Assolute:

MAI market orders

SEMPRE combo order nativo IBKR

MAI aprire gambe separate

EVITARE 09:30-09:45 e 15:30-16:00 EST

6. STRATEGIE CERTIFICATE

6.1 Iron Condor IWM (SMALL Tier)



Parametro	Valore Ottimale	Range	Note

DTE apertura	38 giorni	30-45	Theta/gamma ottimale

Delta short	Â±0.16	Â±0.12/Â±0.20	Simmetria

Width spread	5 punti	4-7	LiquiditÃ  IWM

IVR minimo	45	40-55	Edge VRP

Take Profit	50% credito	45-55%	Gestione disciplinata

Stop Loss	200% credito	150-250%	Protezione capitale

Time Stop	21 DTE	18-24	Evita gamma risk

Performance WFA (2013-2024):

Sharpe OOS mediana: 0.92

5Â° percentile: 0.71

Max DD: <15%

6.2 Bull Put Spread IWM/SPY



Parametro	Valore	Range

DTE	35 giorni	28-42

Delta short	-0.20 (NORMAL), -0.15 (CAUTION)	-0.12/-0.25

Delta long	-0.08	-0.05/-0.12

Width	5 punti (ETF), 2.5 (singoli)	â€”

IVR minimo	30	25-40

Credit/Width	0.35	0.30-0.40

6.3 Matrice Regime â†’ Strategia



Regime	Iron Condor	Bull Put	Wheel	Tail Hedge	Sizing

NORMAL	âœ… Pieno	âœ… Pieno	âœ… CSP	OFF	100%

CAUTION	âš ï¸ Width 4	âœ… +filtro dir.	âœ… Î”0.20	Monitor	50%

SHOCK	âŒ NO	âŒ NO	âš ï¸ CC Fase 3	âœ… ON	0%

7. TIER PROGRESSIONE



Il `capital_tier` (determinato dal capitale disponibile) definisce il tetto massimo delle funzionalità

abilitate. L'`active_mode` è la modalità operativa scelta dall'operatore e può essere uguale o

inferiore al `capital_tier` (es. operare in MICRO con capitale SMALL).



| Tier | Capitale | Strategie | Target mensile | Max posizioni | Milestone req. |

|---|---|---|---|---|---|

| MICRO | €1.000–€2.000 | Bull Put (IWM), Vertical Spread | 0.8–1.5% | 1–2 | R2 |

| SMALL | €2.000–€5.000 | Iron Condor (IWM), Bull Put, Wheel | 1.2–2.5% | 2–3 | R2 |

| MEDIUM | €5.000–€15.000 | Iron Condor (SPY/QQQ), PMCC, Calendar | 1.5–3.0% | 3–5 | R3 |

| ADVANCED | €15.000+ | Multi-sottostante, Ratio Spread | 2.0–4.0% | 4–8 | R5 |



Per la feature matrix completa (ML stack, sizing, execution, UI, upgrade gate) vedi `04_APPENDICI.md`.



8. ROADMAP IMPLEMENTAZIONE



La roadmap è gestita tramite milestone R0–R5 (vedi `config/release_plan_go_nogo.json`

e stato avanzamento in `planner/master_plan.json`).



| Milestone | Obiettivo | Tier abilitato |

|---|---|---|

| R0_BASELINE | Repo stabile, gates verdi | — |

| R1_ENGINE_OFFLINE | Engine offline completo (Research-grade) | — |

| R1B_DEMO_DATA_PIPELINE | Data pipeline demo + LLM extraction | — |

| R2_PAPER_OPERATOR | Paper trading human-confirmed | MICRO, SMALL |

| R3_PAPER_HEDGE | Hedge tattico attivo | MEDIUM |

| R4_GO_NO_GO | GO/NO-GO pack (paper month) | — |

| R5_LIVE_ENABLE | Live enable (human-confirmed) | ADVANCED |



9. METRICHE E KILL SWITCH

Metriche GO/NO-GO



Metrica	Soglia Minima

Sharpe OOS annualizzato	â‰¥ 0.8 (Condor), â‰¥ 0.6 (Bull Put)

Max Drawdown	â‰¤ 15%

Win Rate	â‰¥ 62%

IS/OOS Deflation Ratio	â‰¥ 0.60

Probabilistic Sharpe Ratio	P(SR>0) > 95%

Kill Switch Automatici



Condizione	Azione

DD â‰¥ 20%	Chiusura totale, review

3 stop loss consecutivi	STOP 48h, review regime

Slippage medio > 5 tick	STOP esecuzione, review broker

Model drift (PSI > 0.25) [v11.1]	Alert, retraining obbligatorio

FINE DOCUMENTO MASTER v11.1



## Appendici operative



- Appendice A: Walkthrough Operativo End-to-End (CET) â€“ `03_SETUP.md`

- Appendice B: Moduli Avanzati (Non Canonici) â€“ Delta Overlay â€“ `04_APPENDICI.md`



## Addendum v.T.11.4 â€” Riduzione complessitÃ  & Policy operative



### Pricing Engine Policy (Operational vs Stress)

- **Operational pricing (default/obbligatorio): SVI surface fit** (o spline equivalente con vincoli di stabilitÃ ), per robustezza e performance su dati retail.

- **Heston** Ã¨ ammesso **solo** come **stress/scenario engine** (one-shot), non nel loop operativo giornaliero.



### Minimum Track Record Gate (Kelly)

Kelly puÃ² essere abilitato **solo** se tutte le condizioni sono vere:

- `DATA_MODE == VENDOR_REAL_CHAIN`

- `N_closed_trades >= 50` (trade chiusi, verificati)

- Track record riferito allo stesso strategy family / regime scope dichiarato



Se le condizioni non sono soddisfatte: **fixed fractional obbligatorio**.



### MICRO (Percorso minimo certificabile)

Per utenti retail/entry, il percorso minimo certificabile Ã¨ il tier **MICRO**:

1) Data pipeline underlying (real) + logging

2) Regime classifier base (no HMM)

3) 1 strategia: Bull Put su IWM (o ETF liquido equivalente)

4) Sizing: fixed fractional

5) Kill switch

6) Journal + report

7) Reconciliation (anche semplice) con broker statement

8) Gate test suite â€œliteâ€



La stack completa resta disponibile come evoluzione, ma **non Ã¨ prerequisito** per lâ€™avvio.



### Hedge Policy: Scenario-based constraint (non â€œ% del creditoâ€)

La copertura non Ã¨ definita da una percentuale del credito, ma da vincoli su scenari:

- **Scenario Base**: es. `VIX +30% in 5g`

- **Scenario Shock**: es. `VIX +100% in 10g`

Il budget hedge Ã¨ scelto per mantenere la perdita nello scenario Shock **â‰¤ soglia accettabile** (definita per tier).



### HMM Early-Warning (Claim Policy)

Lâ€™HMM puÃ² essere utilizzato come modulo di **early warning** solo con claim prudente:

- non Ã¨ garantito un anticipo â€œ1â€“2 giorni primaâ€ in modo generale;

- ogni claim di anticipo deve essere supportato dal test **F2-T_HMM_event_OOS** (â‰¥ 2/3 eventi) e da controllo falsi positivi.



### Execution Policy (MICRO vs MEDIUM/ADVANCED)

- **MICRO**: esecuzione semplificata (ordine singolo o ladder aggressiva) su sottostanti liquidi; TWAP/VWAP non richiesti.

- **MEDIUM/ADVANCED**: TWAP/VWAP ammessi quando la liquiditÃ /spread lo giustificano e con logging dei slice.

Nota: su IBKR paper trading i fill parziali non sono rappresentativi; le regole di slicing vanno validate in live con cautela.



### Performance Budget (VaR/CVaR)

Budget dichiarato per ambiente retail:

- **â‰¤ 5 secondi** per portfolio **â‰¤ 10 posizioni** e **10.000 scenari** (Monte Carlo) in modalitÃ  stress/scenario.

Se il portfolio eccede i limiti, Ã¨ richiesto scaling (parallelizzazione / riduzione scenari / repricing approssimato) o il gate fallisce.



## Addendum v.T.11.7 â€” Validator Automation (normativa)



Il progetto adotta un *validator* CLI che rende i gate (Model/Ops/Perf/Policy) ripetibili e certificabili.



Output minimo richiesto per ogni run (Phase 0):

- `reports/phase0_validation_<run_id>.json`

- `reports/phase0_validation_<run_id>.sha256`



Exit codes normativi:

- `0` = PASS

- `2` = WARNING only (**non blocca**, ma run non â€œcertifiedâ€)

- `10` = CRITICAL FAIL (**blocca** lâ€™avanzamento)



Regola: **qualsiasi CRITICAL FAIL blocca**. I WARNING non devono bloccare.



Lâ€™implementazione di riferimento (pseudocodice e struttura report) Ã¨ riportata in Appendice (04_APPENDICI).



## Addendum v.T.11.7 â€” Sizing policy pre-Kelly: Adaptive Fixed Fractional



Per `N_closed_trades < 50` Ã¨ vietato usare Kelly (giÃ  normato). In questa finestra si usa **Adaptive Fixed Fractional**:

- Base sizing: `base_pct` (es. 5% del risk budget per trade)

- Moltiplicatore per macro-regime:

  - NORMAL â†’ 1.0

  - CAUTION â†’ 0.5

  - SHOCK â†’ 0.0 (NO NEW TRADES)



Questa policy evita â€œfalse precisionâ€ su sample piccoli e mantiene progressione MICRO â†’ SMALL â†’ MEDIUM â†’ ADVANCED.



## Addendum v.T.11.7 â€” HMM qualification (non-VIX shocks)



HMM puÃ² essere usato come **monitoring** di default. Lâ€™abilitazione come componente **ensemble che triggera azioni** richiede una *qualification* OOS su famiglie di shock:

1) VIX-driven (es. Feb 2018, Mar 2020)

2) Correlation breakdown (es. Mar 2020, Q1 2022)

3) Credit/geopolitical (es. SVB Mar 2023, Feb 2022)



Gate: HMM deve anticipare (o aggiungere valore rispetto a XGBoost) in **â‰¥ 2/3 famiglie** e non peggiorare i falsi positivi.



## Addendum v.T.11.7 â€” Correlation Regime Detector (feature)



Aggiunta feature semplice e robusta per shock non-VIX:

- Rolling correlation SPYâ€“TLT (es. 60g) + z-score

- Flag `CORRELATION_BREAKDOWN` se z-score < -2Ïƒ (configurabile)



Impatto: riduzione sizing / stop nuove posizioni short-vol quando il breakdown Ã¨ attivo.



## Addendum v.T.11.8 â€” Natura del Ranking Score



Il punteggio composito (0â€“100) misura la **QUALITÃ€ DELLâ€™OPPORTUNITÃ€**, non la **PROBABILITÃ€ DI SUCCESSO**.



Il punteggio aggrega:

- Edge strutturale (IV Rank, skew, term structure)

- FattibilitÃ  esecutiva (liquiditÃ , spread, TCC)

- Rapporto rischio/rendimento della specifica costruzione

- Allineamento con il regime corrente



Il punteggio NON predice:

- Se la singola operazione sarÃ  profittevole

- Lâ€™esatto risultato di P&L

- Il timing di un cambio di regime



**Il ranking ordina i setup da â€œsfavorevoliâ€ a â€œdi alta qualitÃ â€.**

**Non Ã¨ uno strumento di previsione.**



Le performance storiche di setup simili sono fornite come contesto statistico,

non come garanzia. La disciplina operativa e la gestione del rischio

restano il principale determinante dei risultati.



## Automation Boundary Protocol (v.T.11.4+)



### Principio Fondamentale

Il sistema automatizza **tutto ciÃ² che Ã¨ calcolabile e ripetibile**, lasciando all'operatore **solo la selezione consapevole tra alternative presentate in modo trasparente**.



---



### Fase 1: Pre-Ranking (100% Automatizzata)



**Input**: mercato, dati, parametri strategia



**Processo automatizzato**:

1. Data ingestion + quality check (alert se fallisce)

2. Regime classification (XGBoost + HMM; nessun override manuale)

3. Feature engineering (feature set deterministico)

4. Opportunity screening (filtri hard)

5. Scoring composito (pesi validati WFA)

6. Sizing calculation (Kelly solo se gate soddisfatto; altrimenti policy vigente)

7. Risk validation (VaR/CVaR, DD layer, margin check)



**Output**: lista di candidate *ranked*, ciascuna con:

- Score e breakdown

- Sizing raccomandato

- Conseguenze esplicite (max loss, breakeven, time stop, hedge)

- Risk flags (se presenti)



Se la fase fallisce (dati mancanti, drift, errore calcolo):

â†’ `RANKING_SUSPENDED` (nessuna presentazione allâ€™operatore, log obbligatorio).



---



### Fase 2: Ranking e Selezione (Human-in-the-Loop)



Presentazione dashboard con trasparenza su:

- Motivazione dello score (explainability tipo SHAP)

- Conseguenze dellâ€™ingresso (quantificate)

- Costo opportunitÃ  / prossimo scan



Azioni operatore:

- **CONFERMA**

- **RIFIUTA** (motivazione obbligatoria)

- **MODIFICA** (solo riduzione sizing, mai aumento)



Vincoli di sistema:

- Limite posizioni per tier

- Nessuna conferma se DD layer = ORANGE/RED

- Nessuna conferma se regime = SHOCK



---



### Fase 3: Post-Selezione (Automatizzata con Override Controllato)



Dopo conferma:

- Entry protocol

- Monitoring (greeks, P&L, regime)

- Exit protocol (TP/SL/Time/Regime)

- Journaling automatico



Override consentiti:

- Abort entry (pre-fill)

- Force exit (con reason code)

- Kill switch totale



---



### Trasparenza Obbligatoria



Per ogni candidate devono essere esplicitati:



| Elemento | Formato | Esempio |

|----------|---------|---------|

| Max loss teorico | Assoluto + % account | `$455 (9.1%)` |

| Breakeven | Prezzo + % spot | `$142.30 (-4.2%)` |

| Time stop | Data calendario | `2026-03-17 (21 DTE)` |

| Scenario stress | P&L stimato | `VIX+30%: -$340; VIX+100%: -$455` |

| Hedge attivo | SÃ¬/No + costo | `No (CAUTION, DD<10%)` |

| Prossimo check | Orario + trigger | `16:30 CET o VIX+20%` |



Lâ€™operatore non puÃ² confermare senza aver visualizzato tutti gli elementi sopra indicati.





Metodo: applicare scenari VIX storici T5.3 al P&L del portafoglio corrente per stimare gli impatti X (Base) e Y (Shock).







Nota normativa: qualsiasi forma di Kelly parziale, â€œbridgeâ€ o attivazione basata su metriche a breve termine 

(es. Sharpe rolling 30g, win rate su sample ridotto) Ã¨ **esplicitamente vietata**. 

Il Minimum Track Record Gate (â‰¥50 trade chiusi, vendor data + reconciliation) non Ã¨ negoziabile.

