# QOpz.AI — Documento di Progetto Completo v2.0

> **Versione:** v2.0 | **Data:** 2026-03-14
> **Stato:** LIVING DOCUMENT — aggiornare ad ogni milestone completata
> **Nota:** Questo documento integra e supera la visione originale v11.1 con il modulo Opportunity Scanner.
> I file in `.canonici/` restano immutabili (fonte normativa); questo documento è la fonte operativa evolutiva.

---

## 0. Visione del Sistema

QOpz.AI è un sistema quantitativo per il trading di opzioni su azioni e ETF progettato per operatori retail che vogliono lavorare con rigore istituzionale su capitali contenuti (€1k–€20k+).

### Missione

**Non gestire ordini. Trovare, valutare, presentare e — solo dopo conferma esplicita — eseguire.**

Il sistema deve essere capace di:
1. **Scoprire** autonomamente le opportunità di mercato partendo da zero (screening tecnico + chain options reale)
2. **Valutare** ogni opportunità con algoritmi di eccellenza (regime, scoring 4 pilastri, IV Z-Score, Expected Move)
3. **Filtrare** duramente su liquidità, greche, eventi di calendario
4. **Presentare** all'operatore una lista ordinata con trasparenza completa (score breakdown, max loss, breakeven, scenario stress)
5. **Eseguire** solo dopo conferma esplicita (human-in-the-loop, no auto-execution)
6. **Imparare** da ogni trade (EV teorico vs P&L realizzato, bias detection, aggiustamento parametri)

### Principi Non Negoziabili

| Principio | Regola |
|---|---|
| Human-in-the-loop | Il sistema propone, l'operatore conferma. Zero auto-execution |
| Preview/confirm token | Nessun ordine senza token API esplicito |
| Broker come fonte di verità | Greche, IV, bid/ask vengono dal broker — nessun pricing interno per dati operativi |
| DATA_MODE watermark | Ogni report loga `DATA_MODE` (SYNTHETIC o VENDOR_REAL_CHAIN) |
| Kelly gate | Solo con `VENDOR_REAL_CHAIN` AND `N_closed_trades ≥ 50` |
| No market orders | SEMPRE limit + combo nativo IBKR |
| Event trail | Ogni transizione ordine → riga `order_events` |
| Kill switch | `ops/kill_switch.trigger` → arresto immediato |

---

## 1. Architettura del Sistema

Il sistema è composto da **due track paralleli** che convergono nella fase di decisione operatore:

```
╔══════════════════════════════════════════════════════════════════╗
║              TRACK A — OPPORTUNITY DISCOVERY                      ║
║                                                                    ║
║  Market Scanner  →  Option Chain Fetch  →  Filters + Scoring     ║
║  (IBKR/CSV)         (IBKR TWS/paper)       (Liquidity+Greeks)    ║
╚══════════════════════════════╦═══════════════════════════════════╝
                               ║
                               ▼
╔══════════════════════════════════════════════════════════════════╗
║              CONVERGENZA — REGIME + SCORE UNIFICATO               ║
║                                                                    ║
║  Regime (XGBoost+HMM)  +  Score 4 Pilastri  +  IV Z-Score       ║
║  + Expected Move       +  Strategy Selector  +  Sizing            ║
╚══════════════════════════════╦═══════════════════════════════════╝
                               ║
                               ▼
╔══════════════════════════════════════════════════════════════════╗
║              OPERATOR DASHBOARD — HUMAN-IN-THE-LOOP               ║
║                                                                    ║
║  Lista candidati ranked  →  Dettaglio trasparente  →  Conferma   ║
╚══════════════════════════════╦═══════════════════════════════════╝
                               ║
                               ▼
╔══════════════════════════════════════════════════════════════════╗
║              TRACK B — EXECUTION + JOURNAL                        ║
║                                                                    ║
║  Preview Order  →  Confirm Token  →  Smart Limit Ladder          ║
║  → Event Trail  →  Paper Metrics  →  EV vs P&L Tracking          ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 2. Track A — Opportunity Discovery (Modulo Nuovo)

### 2.1 Flusso Completo

```
Step 1: SCREENING TECNICO (pre-market)
  Input: universo simboli (IBKR scanner o lista manuale)
  → Filtro trend: prezzo > MA200
  → Filtro momentum: RSI in zone (<30 o >70)
  → Filtro volatilità compressa: Bollinger width < 10° percentile 6m
  → Filtro volume: > MA20
  Output: lista 5–15 candidati con segnale direzionale

Step 2: OPTION CHAIN FETCH
  Input: candidati da Step 1 + profilo (paper/live)
  → IBKR TWS API: reqSecDefOptParams + reqMktData per strike/expiry
  → Fallback DEV: external_delayed_csv provider
  → Snapshot completo: bid/ask, delta, gamma, theta, vega, IV, OI, volume, underlying
  → Cache snapshot (se orario ≥ 15:30 ET): TTL 18h, marcata "stale" oltre scadenza

Step 3: FILTRI HARD (eliminazione automatica)
  → spread_pct > 10% del mid → SCARTA
  → OI < 100 contratti → SCARTA (hard filter canonico; documento Opp.Scanner suggerisce 500 — applicare 500 in paper/live)
  → DTE < 14 o > 60 giorni → SCARTA (canonico); range ottimale opportunità: 20–45
  → delta fuori range 0.15–0.50 (long direz.) o 0.12–0.30 (credit spread) → SCARTA
  → volume < 10 contratti → SCARTA
  → IVR < 20 → SCARTA (edge statistico nullo)
  → earnings entro 2 giorni → BLOCCO TOTALE
  → earnings 3–7 giorni → FLAG + restrizione strategie long-gamma

Step 4: CALCOLI ANALITICI
  → IV Z-Score 30gg: (IV_oggi - media_30gg) / std_30gg
  → IV Z-Score 60gg: (IV_oggi - media_60gg) / std_60gg
  → Expected Move: (price_call_ATM + price_put_ATM) / underlying_price
  → Confronto segnale tecnico vs Expected Move:
      se segnale > 2× EM → validazione umana OBBLIGATORIA (flag)
  → IV Z-Score interpretation:
      Z < -1.5 → IV cheap → long vega favorito
      Z > +1.5 → IV expensive → short vega favorito
      [-0.5, +0.5] → IV fair → decisione su altri fattori

Step 5: STRATEGY SELECTOR
  Input: segnale direzionale + regime + IV Z-Score + DTE
  → Rialzista + IV alta (Z > +1.5) → BULL PUT SPREAD (credit)
  → Rialzista + IV bassa (Z < -1.5) → BULL CALL SPREAD (debit)
  → Bollinger compresse + breakout incerto → STRADDLE/STRANGLE (se NORMAL)
  → Trend laterale forte → IRON CONDOR (se NORMAL, IVR ≥ 45)
  → CAUTION → solo spread stretti, no iron condor
  → SHOCK → NESSUNA nuova apertura

Step 6: SCORE COMPOSITO (4 Pilastri, già implementato)
  → 35% Vol Edge (IVR/IVP)
  → 25% Liquidità (spread, OI, volume)
  → 25% Risk/Reward struttura
  → 15% Regime Alignment
  → Soglia presentazione: score ≥ 60
  → High Conviction: score ≥ 75 (sizing 1.25× in NORMAL)

Step 7: OUTPUT RANKED LIST
  Top N candidati (default 5) con:
  - Score breakdown (4 pilastri)
  - Strategy selezionata + strikes suggeriti
  - Max loss assoluto + % conto
  - Breakeven prezzo + % da spot
  - Expected Move + distanza segnale
  - IV Z-Score 30/60gg + interpretazione
  - Time stop (21 DTE default)
  - Scenario stress: VIX+30% e VIX+100% → P&L stimato
  - Flag eventi (earnings, macro, dividendi)
  - Qualità dati (real-time / cache / stale)
  - Sizing suggerito (Kelly se abilitato, altrimenti Adaptive Fixed Fractional)
```

### 2.2 Modulo Principale

```
strategy/opportunity_scanner.py
```

**Interface pubblica:**
```python
def scan_opportunities(
    profile: str,                    # "dev" | "paper" | "live"
    regime: str,                     # "NORMAL" | "CAUTION" | "SHOCK"
    symbols: list[str] | None,       # None = usa IBKR scanner
    top_n: int = 5,
    settings_path: str | None = None,
    use_cache: bool = True,
) -> ScanResult

@dataclass
class ScanResult:
    profile: str
    regime: str
    data_mode: str                   # DATA_MODE watermark
    scan_ts: str                     # UTC ISO timestamp
    cache_used: bool
    cache_age_hours: float | None
    candidates: list[OpportunityCandidate]
    filtered_count: int              # quanti scartati dai filtri hard
    ranking_suspended: bool          # True se scan fallisce
    suspension_reason: str | None

@dataclass
class OpportunityCandidate:
    symbol: str
    strategy: str                    # "BULL_PUT" | "IRON_CONDOR" | "STRADDLE" | "BULL_CALL"
    score: float                     # 0–100
    score_breakdown: dict            # {vol_edge, liquidity, risk_reward, regime}
    expiry: str                      # ISO date
    dte: int
    strikes: list[float]
    delta: float
    iv: float
    iv_zscore_30: float
    iv_zscore_60: float
    expected_move: float             # come % del sottostante
    signal_vs_em_ratio: float        # segnale tecnico / expected move
    spread_pct: float
    open_interest: int
    volume: int
    max_loss: float                  # assoluto in $
    max_loss_pct: float              # % del conto
    breakeven: float
    breakeven_pct: float
    credit_or_debit: float
    sizing_suggested: float          # % conto
    kelly_fraction: float | None
    events_flag: str | None          # "EARNINGS_2D" | "EARNINGS_7D" | "DIVIDEND_5D" | None
    human_review_required: bool      # True se signal > 2× EM
    stress_base: float               # P&L stimato VIX+30%
    stress_shock: float              # P&L stimato VIX+100%
    data_quality: str                # "real_time" | "cache" | "stale" | "synthetic"
    source: str                      # "ibkr_paper" | "ibkr_live" | "csv_delayed"
```

### 2.3 Cache Chain Snapshot

- File: `data/cache/option_chain_{symbol}_{date}.json`
- Triggered: automaticamente se ora ≥ 15:30 ET durante scan
- TTL: 18h — oltre → `data_quality = "stale"`, warning esplicito in UI
- Struttura: `{symbol, captured_at_utc, expires_at_utc, contracts: [...]}`

---

## 3. Track B — Execution (già implementato, invariato)

### 3.1 State Machine Ordini

```
NEW → SUBMITTED → ACK → FILLED
              ↘ REJECTED
              ↘ CANCELLED (timeout / abbandono ladder)
```

Ogni transizione → riga `order_events` (event trail obbligatorio).

### 3.2 Smart Limit Order Ladder

| Step | Prezzo | Timeout | Fallback |
|---|---|---|---|
| 1 | Mid | 2 min | Step 2 |
| 2 | Mid − 1 tick | 2 min | Step 3 |
| 3 | Mid − 3 tick | 2 min | Step 4 |
| 4 | Mid − 5 tick | 2 min | Step 5 |
| 5 | Abbandono | — | Rivaluta domani |

### 3.3 Adapter Pattern

- `dev` → `DevSimulationAdapter` (dry_run, no broker)
- `paper` → `PaperLiveAdapterBase` (IBKR paper, port 7496)
- `live` → `PaperLiveAdapterBase` (IBKR live, port 7497)

---

## 4. Regime Detection (già implementato)

### 4.1 Ensemble XGBoost + HMM

| Regime | Condizione | Nuovi trade | Sizing |
|---|---|---|---|
| NORMAL | VIX < 20, contango | Tutte le strategie | 100% |
| CAUTION | VIX 20–28 o backwardation | Spread stretti + filtro direz. | 50% |
| SHOCK | VIX > 28 o HMM P(Shock) > 0.7 | STOP | 0% |

**Regola ensemble:** se XGBoost = CAUTION e HMM P(Shock) > 0.7 → upgrade a SHOCK.

### 4.2 Correlation Breakdown Detector

```python
corr60 = rolling_corr("SPY", "TLT", window=60)
z = zscore(corr60, window=252)
# z < -2.0 → flag CORRELATION_BREAKDOWN → stop short-vol, ridurre sizing
```

---

## 5. Scoring 4 Pilastri (già implementato)

| Pilastro | Peso WFA | Range | Hard Filter |
|---|---|---|---|
| Vol Edge (IVR) | 35% | 28–42% | IVR < 20 → REJECT |
| Liquidità (spread, OI, volume) | 25% | 20–30% | spread > 10% → REJECT |
| Risk/Reward struttura | 25% | 20–30% | credit < 3×TCC → REJECT |
| Regime Alignment | 15% | 10–20% | SHOCK → REJECT |

**Soglie:** score ≥ 60 → presentazione; score ≥ 75 → High Conviction.

---

## 6. Kelly e Sizing

### 6.1 Gate obbligatorio

Kelly abilitato SOLO SE:
- `DATA_MODE == VENDOR_REAL_CHAIN`
- `N_closed_trades >= 50` (trade chiusi, verificati, reconciliati)

Altrimenti: **Adaptive Fixed Fractional** (regime-based, no Kelly).

### 6.2 Adaptive Fixed Fractional (pre-Kelly)

```
base_pct × regime_multiplier
dove regime_multiplier: NORMAL=1.0, CAUTION=0.5, SHOCK=0.0
```

### 6.3 Kelly Fractional (post-gate)

```
f* = (p × b - q) / b
f = 0.5 × f*                    # half-Kelly
f *= 0.8 se skewness < -1.0     # skewness adjustment
f = 0 se f < 0.5% capitale      # lower bound — no trade
f = min(f, 0.25)                 # hard cap 25%
```

---

## 7. Database Schema

### 7.1 Tabelle esistenti (execution track)

| Tabella | Scopo |
|---|---|
| `orders` | Ordini con state machine completa + provenance fields |
| `order_events` | Event trail ogni transizione ordine |
| `paper_trades` | Journal trade paper con greche, regime, kelly, EV |
| `paper_equity_snapshots` | Equity curve giornaliera |
| `operator_opportunity_decisions` | Decisioni operatore (APPROVE/REJECT/MODIFY + note) |
| `compliance_events` | Violazioni regole e circuit breaker |

### 7.2 Nuove tabelle (opportunity track)

**`opportunity_candidates`** — candidati post-scanner, pre-decisione operatore:
```sql
CREATE TABLE opportunity_candidates (
    id               VARCHAR PRIMARY KEY,  -- UUID
    scan_ts          TIMESTAMPTZ NOT NULL,
    profile          VARCHAR NOT NULL,
    symbol           VARCHAR NOT NULL,
    strategy         VARCHAR NOT NULL,
    score            DOUBLE NOT NULL,
    score_vol_edge   DOUBLE,
    score_liquidity  DOUBLE,
    score_rr         DOUBLE,
    score_regime     DOUBLE,
    expiry           DATE,
    dte              INTEGER,
    strikes          JSON,               -- list[float]
    delta            DOUBLE,
    iv               DOUBLE,
    iv_zscore_30     DOUBLE,
    iv_zscore_60     DOUBLE,
    expected_move    DOUBLE,
    signal_vs_em     DOUBLE,
    spread_pct       DOUBLE,
    open_interest    INTEGER,
    volume           INTEGER,
    max_loss         DOUBLE,
    max_loss_pct     DOUBLE,
    breakeven        DOUBLE,
    credit_or_debit  DOUBLE,
    sizing_suggested DOUBLE,
    kelly_fraction   DOUBLE,
    events_flag      VARCHAR,
    human_review_req BOOLEAN DEFAULT FALSE,
    stress_base      DOUBLE,
    stress_shock     DOUBLE,
    data_quality     VARCHAR,            -- real_time|cache|stale|synthetic
    source           VARCHAR,
    regime_at_scan   VARCHAR NOT NULL,
    -- provenance (obbligatorio su tutti i record DuckDB)
    source_system    VARCHAR DEFAULT 'qopz_ai',
    source_mode      VARCHAR NOT NULL,   -- DATA_MODE
    source_quality   VARCHAR NOT NULL,   -- profilo
    asof_ts          TIMESTAMPTZ NOT NULL,
    received_ts      TIMESTAMPTZ NOT NULL
);
```

**`opportunity_chain_snapshots`** — cache chain IBKR per riuso:
```sql
CREATE TABLE opportunity_chain_snapshots (
    id           VARCHAR PRIMARY KEY,
    symbol       VARCHAR NOT NULL,
    captured_at  TIMESTAMPTZ NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    is_stale     BOOLEAN DEFAULT FALSE,
    contracts    JSON NOT NULL,          -- list[OptionContract]
    source       VARCHAR NOT NULL,
    source_mode  VARCHAR NOT NULL,
    received_ts  TIMESTAMPTZ NOT NULL
);
```

**`opportunity_ev_tracking`** — confronto EV teorico vs P&L realizzato:
```sql
CREATE TABLE opportunity_ev_tracking (
    id               VARCHAR PRIMARY KEY,
    candidate_id     VARCHAR NOT NULL,   -- FK → opportunity_candidates.id
    trade_id         VARCHAR,            -- FK → paper_trades.id (quando eseguito)
    ev_at_entry      DOUBLE,             -- EV teorico calcolato all'entry
    win_prob         DOUBLE,             -- probabilità di profitto all'entry
    pnl_realized     DOUBLE,             -- P&L effettivo (da paper_trades)
    ev_error         DOUBLE,             -- pnl_realized - ev_at_entry
    iv_zscore_at_entry DOUBLE,
    em_at_entry      DOUBLE,
    regime_at_entry  VARCHAR,
    strategy         VARCHAR,
    closed_at        TIMESTAMPTZ,
    source_mode      VARCHAR NOT NULL,
    received_ts      TIMESTAMPTZ NOT NULL
);
```

---

## 8. API Endpoints

### 8.1 Endpoint esistenti (invariati)

| Method | Path | Scopo |
|---|---|---|
| POST | `/opz/universe/scan` | Universe scan base (simboli → scoring) |
| POST | `/opz/opportunity/decision` | Operatore approva/rigetta candidato |
| POST | `/opz/execution/preview` | Preview ordine (genera token) |
| POST | `/opz/execution/confirm` | Conferma ordine (consuma token) |
| POST | `/opz/paper/trade` | Registra trade nel journal |
| POST | `/opz/paper/equity_snapshot` | Registra snapshot equity |
| GET  | `/opz/paper/summary` | Report paper metrics + gates |
| GET  | `/opz/last_actions` | Ultimi trade/decisioni/ordini |
| POST | `/opz/bootstrap` | Seed dati demo (solo con `allow_demo=true`) |
| GET  | `/opz/state` | Stato sistema |
| GET  | `/opz/release_status` | Status milestone |
| GET  | `/opz/health` | Health check |

### 8.2 Nuovi endpoint (opportunity track)

| Method | Path | Input | Output |
|---|---|---|---|
| POST | `/opz/opportunity/scan_full` | `{profile, regime, symbols?, top_n, use_cache}` | `ScanResult` |
| GET  | `/opz/opportunity/chain/{symbol}` | query: `profile, expiry?` | chain raw dal broker/cache |
| GET  | `/opz/opportunity/cache/status` | query: `symbol?` | stato cache + age per simbolo |
| GET  | `/opz/opportunity/candidates` | query: `profile, limit, since_ts?` | lista candidati recenti dal DB |
| GET  | `/opz/opportunity/ev_report` | query: `profile, window_days` | report EV vs P&L + bias detection |

---

## 9. Milestones — Piano Completo

### Track Execution (R0–R5) — stato corrente

| Milestone | Steps | Stato |
|---|---|---|
| R0_BASELINE | D2.38–D2.43 | ✅ COMPLETO |
| R1_ENGINE_OFFLINE | F1-T1..T4, F2-T1..T4 | ✅ COMPLETO |
| R1B_DEMO_DATA_PIPELINE | F1-T5..T8, F2-T5 | ✅ COMPLETO |
| R2_PAPER_OPERATOR | F3-T1, F3-T2, F6-T1 | 🔲 PROSSIMO |
| R3_PAPER_HEDGE | F5-T1..T3 | 🔲 |
| R4_GO_NO_GO | F6-T2 | 🔲 |
| R5_LIVE_ENABLE | F6-T3 | 🔲 |

### Track Opportunity Scanner (ROC0–ROC3) — nuovo

| Milestone | ID Steps | Scope | Definition of Done |
|---|---|---|---|
| **ROC0_CHAIN_FOUNDATION** | ROC0-T1..T4 | `strategy/` `scripts/` `tests/` | Chain fetch da IBKR funzionante in paper; filtri hard passano; IV Z-Score validato vs ORATS; unit test 100% pass |
| **ROC1_SCANNER_CORE** | ROC1-T1..T3 | `strategy/` `api/` `tests/` | `scan_full` produce candidati ranked da chain reale; Expected Move calcolato; strategy selector funzionante; test 100% pass |
| **ROC2_EVENTS_CALENDAR** | ROC2-T1..T2 | `scripts/` `strategy/` | Earnings check operativo (SEC EDGAR o IBKR); dividends check; circuit breaker attivo; test pass |
| **ROC3_UI_EV_TRACKING** | ROC3-T1..T3 | `api/` `ui/` `tests/` | Pannello UI "Da Validare" completo; `opportunity_ev_tracking` popolato; report settimanale EV vs P&L; test pass |

#### Steps ROC0 — Chain Foundation

| Step | File | Deliverable |
|---|---|---|
| ROC0-T1 | `strategy/opportunity_scanner.py` | Modulo base: `OptionChainFetcher` (IBKR + CSV fallback), cache JSON, filtri hard |
| ROC0-T2 | `strategy/opportunity_scanner.py` | IV Z-Score 30/60gg + Expected Move ATM straddle |
| ROC0-T3 | `scripts/fetch_iv_history.py` | Fetch storico IV per finestre Z-Score (yfinance/ORATS free) |
| ROC0-T4 | `tests/test_roc0_*.py` | Test suite: filtri, Z-Score, EM, cache; mock IBKR in DEV |

#### Steps ROC1 — Scanner Core

| Step | File | Deliverable |
|---|---|---|
| ROC1-T1 | `strategy/opportunity_scanner.py` | `scan_opportunities()` completo: screening tecnico + chain + filtri + analitici + scoring + strategy selector |
| ROC1-T2 | `api/opz_api.py` + `execution/storage.py` | `POST /opz/opportunity/scan_full` + tabella `opportunity_candidates` + `opportunity_chain_snapshots` |
| ROC1-T3 | `tests/test_roc1_*.py` | Test end-to-end pipeline: da simbolo a candidato ranked |

#### Steps ROC2 — Events Calendar

| Step | File | Deliverable |
|---|---|---|
| ROC2-T1 | `scripts/events_calendar.py` | Fetch earnings dates (SEC EDGAR API) + dividends; blocco automatico <2gg |
| ROC2-T2 | `tests/test_roc2_*.py` | Test blocco earnings, flag 3–7gg, dividends check |

#### Steps ROC3 — UI + EV Tracking

| Step | File | Deliverable |
|---|---|---|
| ROC3-T1 | `ui/src/` | Pannello "Da Validare": lista candidati ranked, breakdown score, greche, IV Z-Score, EM, flags |
| ROC3-T2 | `execution/storage.py` + `api/opz_api.py` | Tabella `opportunity_ev_tracking`; `GET /opz/opportunity/ev_report` |
| ROC3-T3 | `tests/test_roc3_*.py` | Test UI snapshot, EV tracking, report settimanale |

---

## 10. Connessione IBKR / TWS

### 10.1 Setup

- TWS deve essere avviato **manualmente e esternamente** (non gestito dall'applicativo)
- Port: **7496** (paper), **7497** (live) — configurabili in `config/paper.toml`, `config/live.toml`
- Client ID: 7 (default, configurabile)
- Library: `ib_insync >= 0.9.86` (già in `requirements-broker-ib.txt`)

### 10.2 Meccanismo di connessione (esistente)

```python
# TCP pre-check prima di importare ib_insync
# → lazy import solo se TWS risponde
# → ibkr_tws.py: connect(host, port, clientId, timeout=10s, readonly=False)
# → probes: accountSummary() + positions()
```

### 10.3 Fetch chain options (pattern già in ibkr_combo.py)

```python
ib.qualifyContracts(stock)
params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
# → itera su params per scegliere expiry in range [min_dte, max_dte]
# → per ogni strike: reqMktData(opt, "", snapshot=True) → bid/ask/delta/iv/OI/volume
```

### 10.4 Fallback DEV

In profilo `dev`, la connessione IBKR non è disponibile.
Si usa `execution/providers/external_delayed_provider.py` con CSV:
```
data/providers/external_delayed_quotes.csv
```
Schema CSV: `symbol, asset_type, last, bid, ask, iv, open_interest, volume, delta, gamma, theta, vega, rho, underlying_price, observed_at_utc`

---

## 11. DATA_MODE Policy

| Modalità | Contesto | Kelly | Pricing | Risultati |
|---|---|---|---|---|
| `SYNTHETIC_SURFACE_CALIBRATED` | DEV / engineering | ❌ DISABILITATO | SVI su proxy | Non interpretabili come edge reale |
| `VENDOR_REAL_CHAIN` | PAPER / LIVE | ✅ Solo se N≥50 | SVI su dati reali broker | Certificabili |

Ogni record DuckDB deve avere i 5 campi di provenance:
`source_system`, `source_mode`, `source_quality`, `asof_ts`, `received_ts`

---

## 12. Parametri Operativi Default

### Filtri Hard (non modificabili senza evidenza WFA)

| Filtro | Soglia | Nota |
|---|---|---|
| Spread bid-ask | > 10% mid → SCARTA | Ideale < 5% ATM |
| Open Interest | < 100 (canonico) / < 500 (paper+) | 100 per DEV, 500 per paper/live |
| DTE | < 14 o > 60 → SCARTA | Range ottimale operativo: 20–45 |
| Earnings | < 2 giorni → BLOCCO | 3–7 giorni → FLAG |
| IVR | < 20 → SCARTA | Edge nullo |
| Margine | > 30% capitale → SCARTA | Position sizing eccessivo |
| TCC | Credit < 3×TCC → SCARTA | Trade matematicamente unprofitable |

### Delta Target per Strategia

| Strategia | Delta short | Delta long |
|---|---|---|
| Bull Put / Bear Call (credit) | −0.20 NORMAL, −0.15 CAUTION | −0.08 |
| Iron Condor | ±0.16 (range ±0.12/±0.20) | — |
| Long direzionali | 0.15–0.50 | — |

### IV Z-Score Soglie

| Z-Score | Interpretazione | Azione |
|---|---|---|
| < −1.5 | IV economica | Favorisce long vega |
| −0.5 a +0.5 | IV fair | Neutro |
| > +1.5 | IV costosa | Favorisce short vega |

### Circuit Breaker (ROC — da implementare in ROC2)

| Trigger | Azione |
|---|---|
| Bias EV > 20% su una strategia | Stop strategia + revisione manuale |
| > 30% opportunità con spread > 15% | Stop + avviso liquidità anomala |
| VIX +20% in una sessione | Modalità validazione umana obbligatoria 24h |
| Cache > 50% tickers in sessione | Stop + refresh manuale |

---

## 13. Metriche di Successo

### Per milestone PT1_MICRO (€1k–€2k)

| Metrica | Soglia GO |
|---|---|
| Sharpe OOS annualizzato | ≥ 0.8 |
| Max Drawdown | ≤ 8% (go/no-go paper) / ≤ 15% (limite assoluto) |
| Win Rate paper | ≥ 62% |
| IS/OOS Deflation Ratio | ≥ 0.60 |
| Probabilistic Sharpe Ratio | P(SR>0) > 95% |
| Violazioni regole | ZERO |

### Per modulo Opportunity Scanner (ROC)

| Metrica | Soglia |
|---|---|
| Candidati presentati per sessione | 5–10 (selettività) |
| Validazioni umane rispetto a segnali | 20%–40% (filtro efficace) |
| Bias EV (EV teorico vs P&L realizzato) | < ±15% per strategia |
| Database validazioni accumulate | ≥ 100 prima di ROC3 completo |
| Algoritmo vs scelta operatore | ≥ 80% concordanza (dopo 100 validazioni) |

---

## 14. Kill Switch e Sicurezza

### Livelli di stop

| Livello | Trigger | Azione |
|---|---|---|
| Giallo | Drawdown 10% | Sizing −50%, hedge review |
| Arancione | Drawdown 15% | STOP nuove posizioni, hedge obbligatorio |
| Rosso | Drawdown 20% | Kill switch totale, chiusura posizioni |
| Kill switch operativo | `ops/kill_switch.trigger` esiste | Arresto immediato, nessun nuovo ordine |

### Regole esecuzione assolute

- MAI market orders
- SEMPRE combo order nativo IBKR (no gambe separate)
- EVITARE 09:30–09:45 e 15:30–16:00 EST
- Nessun ordine senza preview/confirm token

---

## 15. Stack Tecnologico

| Layer | Tool | Versione | Note |
|---|---|---|---|
| Language | Python | 3.11+ | |
| Database | DuckDB | latest | Dev + single-operator production |
| Broker API | ib_insync | ≥ 0.9.86 | TWS avviato esternamente |
| ML Regime | XGBoost + hmmlearn | 2.0+ / 0.3+ | |
| Pricing stress | QuantLib-Python | 1.32+ | Solo stress/scenario, non operativo |
| Pricing operativo | SVI surface fit | — | Default per dati retail |
| Market data | yfinance, CBOE, FRED | latest | Free tier |
| IV history | ORATS free / yfinance | — | Per Z-Score windows |
| Events calendar | SEC EDGAR API | — | Earnings dates |
| Dashboard | React + Vite (TypeScript) | 18.x / 5.x | Operator console |
| API | FastAPI + uvicorn | latest | |
| Test | pytest + pytest-asyncio | ≥ 8.0 | |

---

## 16. Note Operative

### Ordine di implementazione consigliato

```
ROC0 (chain foundation) → R2 (paper operator) → ROC1 (scanner core)
→ ROC2 (events) → R3 (hedge) → ROC3 (UI+EV) → R4 (go/no-go)
```

ROC0 precede R2 perché R2 (paper trading reale) beneficia enormemente di avere già il chain fetcher funzionante per valutare i candidati con dati veri prima di eseguire.

### Gestione dati in DEV

- Demo data (bootstrap): 60 equity snapshots + 20 trade demo
- Chain data DEV: CSV fallback con dati delayed sintetici
- Tutti i risultati DEV watermarked `SYNTHETIC_SURFACE_CALIBRATED`
- Nessun sizing economico interpretabile in DEV

### Pre-commit obbligatorio

```bash
python tools/planner_guard.py check --check-target index
python tools/run_gates.py --skip-manifest --skip-certify
python scripts/quick_audit.py --scope all --severity HIGH
```

---

*Documento generato il 2026-03-14. Aggiornare questo file ad ogni milestone completata o cambio architetturale significativo.*
