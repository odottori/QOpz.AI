# QuantOptionAI Ã¢â‚¬â€ TEST (Strategia + Suite)
_Versione: v.T.11.13

---

## 1) Strategia Test

Questo documento definisce **processo + gating** per certificare la qualitÃƒÂ  per fase/modulo.
La suite di dettaglio ÃƒÂ¨ in: `03_TEST_SUITE_vK11_2_CANON.md`.

## Principi
- **CRITICAL fail = STOP**
- **RipetibilitÃƒÂ ** (seed/versioning/run_id)
- **TracciabilitÃƒÂ ** (ogni requisito critico Ã¢â€ â€™ test ID)
- **Ambienti separati**: DEV (synthetic), STAGING (paper), PROD (live)

## Ambienti e dataset
### DEV (mockup/studio)
- DB: **DuckDB** + Parquet
- Dati: **sintetici marcati** (+ opzionale storico gratuito)
- Obiettivo: validare pipeline/feature/regime/risk/UX senza dipendenze esterne

### STAGING (paper)
- Dati: **real-time broker** (catena opzioni + greche affidabili)
- Obiettivo: validare execution, slippage, journaling, kill switch in condizioni realistiche

### PROD (live)
- Come STAGING + monitoraggio drift e regression

## Gates
- Data Gate: completezza/plausibilitÃƒÂ /latenza/fonte
- Model Gate: accuracy OOS + calibration + drift PSI/CSI
- Execution Gate: ladder/TWAP/VWAP, spread reject, nessun ordine sporco
- Risk Gate: DD triggers + kill switch + hedge cost rule
- Ops Gate: logging/audit trail/backup+recovery test

## 2) Test Suite (vK.11.2)

QUANTOPTION AI vk.11.2 Ã¢â‚¬â€ TEST SUITE
Documento di Certificazione e Validazione
Version: v.T.11.12
Data: 2026-02-24
Scopo: Definire test dettagliati per certificare ogni fase implementativa
INDICE TEST SUITE
Framework Testing
Fase 1: Pipeline Dati (Settimane 1-2)
Fase 2: Regime Detection (Settimane 3-4)
Fase 3: Paper Trading Setup (Settimane 5-6)
Fase 4: Scoring e Kelly (Settimane 7-10)
Fase 5: Microstructure (Settimane 11-12)
Fase 6: Paper Trading Completo (Settimane 13+)
Test Continuativi (Produzione)
Checklist Finali GO/NO-GO
1. FRAMEWORK TESTING
1.1 Tipologie di Test
Tipo	Descrizione	Quando Applicare
Unit Test	Validazione singola funzione/classe	Ogni componente
Integration Test	Validazione interazione componenti	A modulo completato
System Test	Validazione sistema end-to-end	A fase completata
Regression Test	Verifica non-breakage funzionalitÃƒÂ  esistenti	Dopo ogni modifica
Stress Test	Validazione comportamento sotto carico	Pre-produzione
1.2 Criteri di Pass/Fail
Livello	Criterio	Azione se Fail
CRITICAL	Bloccante, sistema non operabile	STOP, fix obbligatorio
HIGH	Degradazione significativa performance	Fix prima proseguire
MEDIUM	FunzionalitÃƒÂ  ridotta ma sistema operabile	Fix entro fine fase
LOW	Cosmetic/minor	Fix entro release successiva
1.3 Ambiente di Test
Ambiente	Descrizione	Uso
Dev	Locale, DuckDB, dati storici	Sviluppo, unit test
Staging	VPS, PostgreSQL, paper trading	Integration, system test
Production	VPS, PostgreSQL, live trading	Solo post-certificazione
2. FASE 1: PIPELINE DATI (Settimane 1-2)
2.1 Test 1.1 Ã¢â‚¬â€ Ingestione Dati di Mercato
ID: F1-T1
Tipo: Integration
PrioritÃƒÂ : CRITICAL
Step	Azione	Risultato Atteso	Pass Criteria
1	Esegui ingestion SPY giornaliero	Dati salvati in market_data	0 errori, 100% righe
2	Verifica campi OHLCV	Tutti i campi popolati	Nessun NULL
3	Verifica date consecutive	No gap > 2 giorni	Gap rilevati = 0
4	Test split adjustment	Pre/post split coerenti	Adj_close corretto
Dati di Test: SPY 2020-01-02 (split 4:1 2022-06-06)
Output Richiesto: Log ingestion, report completezza
2.2 Test 1.2 Ã¢â‚¬â€ Calcolo IV Rank
ID: F1-T2
Tipo: Unit + Integration
PrioritÃƒÂ : CRITICAL
Step	Azione	Risultato Atteso	Pass Criteria
1	Calcola IVR SPY con 252g lookback	Valore tra 0 e 100	0 Ã¢â€°Â¤ IVR Ã¢â€°Â¤ 100
2	Confronto con ORATS ground truth	Differenza assoluta	|IVR_calc - IVR_ORATS| < 5%
3	Test edge case: IV costante	IVR = 50 (o gestito)	No divisione per zero
4	Test edge case: nuovo ticker	Gestione gracefully	Alert, no crash
Dati di Test: SPY, IWM, QQQ (ultimi 252 giorni)
Ground Truth: ORATS free tier
2.3 Test 1.3 Ã¢â‚¬â€ QualitÃƒÂ  Dati Options Chain
ID: F1-T3
Tipo: Integration
PrioritÃƒÂ : HIGH
Check	Condizione	Azione se Fail
bid Ã¢â€°Â¤ ask	SEMPRE	Esclude strike, alert
Delta put Ã¢Ë†Ë† [-1, 0]	SEMPRE	Esclude, log warning
Delta call Ã¢Ë†Ë† [0, 1]	SEMPRE	Esclude, log warning
IV Ã¢Ë†Ë† (0, 5)	SEMPRE	Verifica manuale
Put-call parity	|C-P-S+KÃ‚Â·e^(-rT)| < soglia	Alert sistematico
Campionamento: 100 strike random per 5 giorni
2.4 Test 1.4 Ã¢â‚¬â€ Database Integrity
ID: F1-T4
Tipo: System
PrioritÃƒÂ : CRITICAL
Test	Query	Risultato Atteso
Chiavi primarie uniche	SELECT COUNT(*), COUNT(DISTINCT pk) FROM table	Uguali
Foreign key integrity	Check referenziali	0 violazioni
Timestamp coerenti	MAX(date) - MIN(date)	Range atteso
Performance query	SELECT con JOIN principali	< 100ms
2.5 Certificazione Fase 1
Metrica	Soglia	Stato
Errori ingestion	0	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Discrepanza IVR vs ORATS	< 5%	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Data quality checks	100% pass	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Query performance	< 100ms	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Firma: _______________ Data: _______
3. FASE 2: REGIME DETECTION (Settimane 3-4)
3.1 Test 2.1 Ã¢â‚¬â€ XGBoost Regime Classifier
ID: F2-T1
Tipo: Unit + System
PrioritÃƒÂ : CRITICAL
Step	Azione	Risultato Atteso	Pass Criteria
1	Training su fold 2010-2013	Modello salvato	No errori
2	Predict su 2014 (OOS)	3 classi output	Accuracy > 65%
3	Calibrazione probabilitÃƒÂ 	Platt scaling applicato	Brier score < 0.2
4	Feature importance SHAP	Top 3 coerenti con attese	VIX/VIX3M in top 3
Metriche di Output:
Accuracy OOS: ___
F1-macro: ___
Confusion matrix: salvata
3.2 Test 2.2 Ã¢â‚¬â€ HMM Ensemble [v11.1]
ID: F2-T2
Tipo: Unit + Integration
PrioritÃƒÂ : HIGH
Step	Azione	Risultato Atteso	Pass Criteria
1	Fit HMM su 252g rolling	3 stati identificati	Convergenza
2	Decode stati nascosti	Sequenza stati	Coerente con VIX
3	Matrice transizione	P(iÃ¢â€ â€™j) per ogni coppia	Somma righe = 1
4	Early warning shock	HMM P(Shock)>0.7 prima XGBoost	Lead time 1-2g in Ã¢â€°Â¥ 2/3 famiglie di shock (event-based) e valore netto vs XGBoost
Validazione Visuale: Plot stati HMM vs VIX, evidenziare lead time
3.3 Test 2.3 Ã¢â‚¬â€ Ensemble Integration
ID: F2-T3
Tipo: Integration
PrioritÃƒÂ : HIGH
Scenario	XGBoost	HMM	Output Ensemble	Atteso
1	NORMAL	P(Shock)=0.8	CAUTION	Upgrade
2	CAUTION	P(Shock)=0.3	CAUTION	No change
3	CAUTION	P(Shock)=0.8	SHOCK	Upgrade
4	NORMAL	P(Shock)=0.2	NORMAL	No change
Pass Criteria: 100% scenari corretti
3.4 Test 2.4 Ã¢â‚¬â€ WFA Backtest Bull Put
ID: F2-T4
Tipo: System
PrioritÃƒÂ : CRITICAL
Parametro	Valore Test
Strategia	Bull Put IWM
Periodo	2010-2024
Fold	10 (3y IS, 1y OOS)
Metriche	Sharpe, Max DD, Win Rate
Metrica	Soglia Minima	Risultato	Pass
Sharpe OOS mediano	Ã¢â€°Â¥ 0.60	___	Ã¢ËœÂ
Max DD OOS	Ã¢â€°Â¤ 15%	___	Ã¢ËœÂ
Win Rate	Ã¢â€°Â¥ 55%	___	Ã¢ËœÂ
IS/OOS Deflation	Ã¢â€°Â¥ 0.60	___	Ã¢ËœÂ
Anni OOS negativi	0 con DD > 20%	___	Ã¢ËœÂ
Output Richiesto:
Equity curve OOS concatenato
Distribuzione Sharpe per fold
Drawdown plot
3.5 Certificazione Fase 2
Componente	Test ID	Stato
XGBoost	F2-T1	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
HMM	F2-T2	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Ensemble	F2-T3	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
WFA Bull Put	F2-T4	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Firma: _______________ Data: _______
4. FASE 3: PAPER TRADING SETUP (Settimane 5-6)
4.1 Test 3.1 Ã¢â‚¬â€ Connessione IBKR API
ID: F3-T1
Tipo: Integration
PrioritÃƒÂ : CRITICAL
Step	Azione	Risultato Atteso	Pass Criteria
1	Connessione TWS/Gateway	Connected	No timeout
2	Richiesta account info	Balance, buying power	Dati corretti
3	Richiesta posizioni	Lista posizioni	Coerente con TWS
4	Keepalive 24h	Connessione stabile	0 disconnessioni
4.2 Test 3.2 Ã¢â‚¬â€ Ordini Combo Multi-Leg
ID: F3-T2
Tipo: System
PrioritÃƒÂ : CRITICAL
Step	Azione	Risultato Atteso	Pass Criteria
1	Crea ordine Bull Put 2 gambe	Ordine combo valido	Legs corretti
2	Invio paper order	Ordine ricevuto	OrderId assegnato
3	Modifica prezzo limit	Update ricevuto	Prezzo aggiornato
4	Cancella ordine	Ordine cancellato	Status = Cancelled
5	Fill simulato	Posizione aperta	P&L calcolato
Test su: IWM, SPY (1 contratto ciascuno)
4.3 Test 3.3 Ã¢â‚¬â€ Protocollo Esecuzione Smart
ID: F3-T3
Tipo: System
PrioritÃƒÂ : HIGH
Step	Condizione	Azione Sistema	Verifica
1	Spread < 10%	Ladder Step 1 (Mid)	Timeout 2min, fallback
2	No fill Step 1	Ladder Step 2 (Mid-1)	Esecuzione corretta
3	No fill fino Step 4	Ladder Step 5 (Abbandono)	No ordini pendenti
4	Spread > 10%	REJECT immediato	Alert, no ordine
4.4 Test 3.4 Ã¢â‚¬â€ Logging e Journal
ID: F3-T4
Tipo: Integration
PrioritÃƒÂ : MEDIUM
Verifica	Query/Check	Risultato Atteso
Ogni ordine loggato	SELECT COUNT(*) FROM orders	= ordini inviati
Fill price registrata	SELECT fill_price FROM orders	Ã¢â€°Â  NULL per filled
Slippage calcolato	(fill_price - limit_price)/limit_price	Valore realistico
Timestamp precisi	ORDER BY timestamp	Sequenza corretta
4.5 Certificazione Fase 3
Metrica	Soglia	Stato
Connessione API stabile	24h	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Ordini combo eseguiti	5 senza errori	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Protocollo ladder	100% corretto	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Logging completo	100% ordini	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Firma: _______________ Data: _______
5. FASE 4: SCORING E KELLY (Settimane 7-10)
5.1 Test 4.1 Ã¢â‚¬â€ Score Composito 4 Pilastri
ID: F4-T1
Tipo: Unit
PrioritÃƒÂ : HIGH
Input Test	Peso	Range Score	Risultato Atteso
IVR=50, LiquiditÃƒÂ =alta, R/R=2.0, Regime=NORMAL	35/25/25/15	60-80	Score calcolato
IVR=15 (bassa)	Ã¢â‚¬â€	<60	REJECT (filtro hard)
Spread=12%	Ã¢â‚¬â€	REJECT	Filtro hard attivo
Verifica pesi: Somma = 100%, calcolo aritmetico corretto
5.2 Test 4.2 Ã¢â‚¬â€ Kelly Fractional [v11.1]
ID: F4-T2
Tipo: Unit
PrioritÃƒÂ : CRITICAL
Scenario	Parametri	Risultato Atteso
Base	p=0.65, b=1.5, cap=10000	f=0.5*(0.65*1.5-0.35)/1.5=0.208 Ã¢â€ â€™ 20.8%
Skewness <-1.0	skew=-1.5	f ridotto 20% Ã¢â€ â€™ 16.6%
Lower bound	f_calc=0.3%, min_trade=0.5%	NO TRADE (return 0)
Upper bound	f_calc=35%	Cap a 25%
Unit test: 10 scenari edge case
5.3 Test 4.3 Ã¢â‚¬â€ Confronto Performance
ID: F4-T3
Tipo: System
PrioritÃƒÂ : HIGH
Configurazione	Periodo Test	Sharpe Atteso
Solo Regime (base)	60g paper	Baseline
Regime + Scoring	60g paper	Baseline + 0.10
Regime + Scoring + Kelly	60g paper	Baseline + 0.15
Pass Criteria: Miglioramento Ã¢â€°Â¥ 0.10 Sharpe vs baseline
5.4 Certificazione Fase 4
Componente	Test ID	Stato
Scoring 4 pilastri	F4-T1	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Kelly fractional	F4-T2	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Miglioramento performance	F4-T3	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Firma: _______________ Data: _______
6. FASE 5: MICROSTRUCTURE (Settimane 11-12)
6.1 Test 5.1 Ã¢â‚¬â€ Feature Microstructure [v11.1]
ID: F5-T1
Tipo: Unit
PrioritÃƒÂ : MEDIUM
Feature	Input Test	Output Atteso	Validazione
Volume Profile Delta	Tick data bid/ask	Ratio [-1, 1]	Correlazione con direzione
OI Change Velocity	OI t, OI t-3	% change annualizzato	Spike >2ÃÆ’ rilevati
IV Curvature Accel	Skew 5g	Accelerazione	Leading VIX 1-2g
6.2 Test 5.2 Ã¢â‚¬â€ TWAP Execution [v11.1]
ID: F5-T2
Tipo: System
PrioritÃƒÂ : MEDIUM
Condizione	Azione	Verifica
Spread > $0.50 su 4-gambe	Attiva TWAP	3 slice create
Esecuzione slice 1	Fill o timeout 5min	Log timestamp
Esecuzione slice 2	5min dopo slice 1	Intervallo corretto
Completezza	Tutte le slice eseguite	Posizione aperta
6.3 Test 5.3 Ã¢â‚¬â€ Drawdown Control Simulation
ID: F5-T3
Tipo: System
PrioritÃƒÂ : CRITICAL
Scenario Simulato	DD Raggiunto	Azione Sistema	Verifica
DD 10%	10%	Alert giallo, sizing 50%	Log alert
DD 15%	15%	STOP nuove posizioni, hedge ON	Blocco ordini
DD 20%	20%	Kill switch, chiusura totale	Posizioni chiuse
Simulazione: Manipolazione P&L storico per triggerare livelli
6.4 Certificazione Fase 5
Componente	Test ID	Stato
Features microstructure	F5-T1	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
TWAP execution	F5-T2	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
DD control	F5-T3	Ã¢ËœÂ PASS Ã¢ËœÂ FAIL
Firma: _______________ Data: _______
7. FASE 6: PAPER TRADING COMPLETO (Settimane 13+)
7.1 Test 6.1 Ã¢â‚¬â€ Paper Trading 60 Giorni
ID: F6-T1
Tipo: System (Live)
PrioritÃƒÂ : CRITICAL
Metrica	Soglia Minima	Target	Risultato
Numero trade	Ã¢â€°Â¥ 20	Ã¢â€°Â¥ 30	___
Win rate	Ã¢â€°Â¥ 55%	Ã¢â€°Â¥ 60%	___
Profit factor	Ã¢â€°Â¥ 1.3	Ã¢â€°Â¥ 1.5	___
Sharpe annualizzato	Ã¢â€°Â¥ 0.6	Ã¢â€°Â¥ 0.8	___
Max drawdown	Ã¢â€°Â¤ 15%	Ã¢â€°Â¤ 10%	___
Slippage medio	Ã¢â€°Â¤ 3 tick	Ã¢â€°Â¤ 2 tick	___
7.2 Test 6.2 Ã¢â‚¬â€ Journal Completo
ID: F6-T2
Tipo: Integration
PrioritÃƒÂ : HIGH
Entry Obbligatorio	Presente	Dettaglio
Data/ora entry	Ã¢ËœÂ
Simbolo, strategia, strikes	Ã¢ËœÂ
Regime at entry	Ã¢ËœÂ
Score at entry	Ã¢ËœÂ
Kelly sizing usato	Ã¢ËœÂ
P&L realized	Ã¢ËœÂ
Slippage actual	Ã¢ËœÂ
Exit reason (TP/SL/Time)	Ã¢ËœÂ
Note operative	Ã¢ËœÂ
7.3 Test 6.3 Ã¢â‚¬â€ Stress Test Live
ID: F6-T3
Tipo: System
PrioritÃƒÂ : HIGH
Scenario	Simulazione	Risposta Sistema
VIX spike +20% in 1g	Dati storici 2020-02-24	Regime Ã¢â€ â€™ SHOCK, hedge ON
Gap down -5% overnight	Simulazione P&L	DD check, possibile kill switch
API disconnessione	Disconnessione forzata	Reconnect automatico, alert
7.4 Certificazione Fase 6 (GO/NO-GO Finale)
Criterio	Soglia	Risultato	Stato
Sharpe 60g	Ã¢â€°Â¥ 0.6	___	Ã¢ËœÂ
Max DD	Ã¢â€°Â¤ 15%	___	Ã¢ËœÂ
Win rate	Ã¢â€°Â¥ 55%	___	Ã¢ËœÂ
Completezza journal	100%	___	Ã¢ËœÂ
Zero errori esecuzione	0	___	Ã¢ËœÂ
DECISIONE FINALE: Ã¢ËœÂ GO (procedi a live) Ã¢ËœÂ NO-GO (revisione)
Firma: _______________ Data: _______
8. TEST CONTINUATIVI (Produzione)
8.1 Monitoraggio Giornaliero
Check	Frequenza	Soglia Alert	Azione
Dati ingestion	Ogni 30 min	> 30 min delay	Alert Telegram
Model accuracy	Giornaliero	< 55% (20g rolling)	Review regime
PSI drift	Giornaliero	> 0.25	Retraining
P&L vs backtest	Settimanale	Sharpe < 0.5 (30g)	Review completa
Slippage medio	Per trade	> 5 tick	Review broker
8.2 Regression Test Mensile
Test	Scopo
Re-run WFA ultimo anno	Verifica robustezza parametri
Backtest su scenario stress 2008/2020	Sopravvivenza regime estremo
Check data quality 100%	Completezza, plausibilitÃƒÂ 
8.3 Annual Review
AttivitÃƒÂ 	Output
Re-ottimizzazione parametri WFA	Nuovi parametri certificati
Review feature importance SHAP	Feature selection aggiornata
Stress test aggiornato	Nuovi scenari (es. 2023 banking crisis)
9. CHECKLIST FINALI GO/NO-GO
Pre-Paper (Fine Fase 2)
#	Item	Stato
1	WFA Bull Put Sharpe > 0.6	Ã¢ËœÂ
2	XGBoost accuracy OOS > 65%	Ã¢ËœÂ
3	Database integrity 100%	Ã¢ËœÂ
4	Pipeline dati automatico	Ã¢ËœÂ
Pre-Live (Fine Fase 6)
#	Item	Stato
1	60g paper Sharpe > 0.6	Ã¢ËœÂ
2	Max DD < 15%	Ã¢ËœÂ
3	Win rate > 55%	Ã¢ËœÂ
4	Journal completo	Ã¢ËœÂ
5	Zero errori critici	Ã¢ËœÂ
6	Kill switch testato	Ã¢ËœÂ
7	Documentazione aggiornata	Ã¢ËœÂ
FINE TEST SUITE vk.11.2

## 3) Traceability Matrix

| Fase | Modulo | Test IDs | Gate |
|---|---|---|---|
| Phase 0 | Setup/Env/DuckDB/Synthetic | P0-001..P0-041 | Operational readiness |
| Fase 1 | Pipeline dati + qualitÃƒÂ  + DB | F1-T1..F1-T4 | Data Gate |
| Fase 2 | Regime (XGB+HMM) + WFA | F2-T1..F2-T4 | Model Gate |
| Fase 3 | Paper trading + IBKR exec | F3-T1..F3-T4 | Execution Gate |
| Fase 4 | Scoring + Kelly + filtri hard | F4-T1..F4-T3 | Edge/Sizing Gate |
| Fase 5 | Microstructure + TWAP + DD sim | F5-T1..F5-T3 | Stress/Risk Gate |
| Fase 6 | Paper 60g + GO/NO-GO | F6-T1..F6-T3 | Go-live Gate |
| Produzione | Monitor/Regression/Annual | 8.* + 9.* | Continuous certification |



---

## v.T.11.3 Ã¢â‚¬â€ Addendum (Hardening)

### DATA_MODE (obbligatorio)
Ogni run deve dichiarare `DATA_MODE`:

- `SYNTHETIC_SURFACE_CALIBRATED` Ã¢â€ â€™ engineering validation (**NOT execution-grade**)
- `VENDOR_REAL_CHAIN` Ã¢â€ â€™ execution-grade

**Vincolo**: se `DATA_MODE == SYNTHETIC_SURFACE_CALIBRATED` allora `Kelly_enabled = False` (test obbligatorio).

### Nuovi test obbligatori (v.T.11.3)
- `F2-T_leakage_guard` Ã¢â‚¬â€ anti look-ahead su percentili/threshold regime
- `F2-T_HMM_event_OOS` Ã¢â‚¬â€ early-warning OOS event-based su shock storici catalogati
- `PERF_VaR_runtime_budget` Ã¢â‚¬â€ budget runtime risk engine (Heston/MC)
- `OPS_reconciliation` Ã¢â‚¬â€ reconciliation P&L vs IBKR statement (fixture)
- `DATA_MODE_Kelly_block` Ã¢â‚¬â€ hard fail se Kelly attivo su SYNTHETIC

### Hotfix v.T.11.3.1 Ã¢â‚¬â€ Kelly lower bound (chiarezza semantica)
- Regola: **NO TRADE** se `f_calc < min_trade_pct/100` (es. 0.3% < 0.5%).
- Implementazione: confronto diretto su `f`, senza moltiplicare per `capital`.

| Fase 2 (hardening) | Anti-leakage + HMM OOS | F2-T_leakage_guard, F2-T_HMM_event_OOS | Model Gate |
| Cross-fase | Kelly block + VaR perf + Reconciliation | DATA_MODE_Kelly_block, PERF_VaR_runtime_budget, OPS_reconciliation | Ops Gate |

### Addendum v.T.11.4 Ã¢â‚¬â€ Nuovi Gate (operational simplification & robustness)
- **F1-T_margin_efficiency_metric**: journal/report include `Avg_Margin_Used` e `MarginEfficiency`.
- **F4-T_min_track_record_kelly**: Kelly abilitabile solo se `DATA_MODE=VENDOR_REAL_CHAIN` e `N_closed_trades>=50`.
- **PERF_pricing_operational_latency**: pricing operativo (SVI) entro budget runtime dichiarato.
- **POLICY_Hedge_scenario_template**: run invalido se non sono dichiarati Scenario Base/Scenario Shock e cap shock.

#### Traceability Matrix Ã¢â‚¬â€ righe aggiuntive (v.T.11.4)
| Fase 4 (risk) | Track record gate + Hedge scenario policy | F4-T_min_track_record_kelly, POLICY_Hedge_scenario_template | Ops Gate |
| Cross-fase | Pricing operativo SVI + Margin Efficiency | PERF_pricing_operational_latency, F1-T_margin_efficiency_metric | Model Gate |

### Addendum v.T.11.4.1 Ã¢â‚¬â€ Quantificazione performance gate
- **PERF_VaR_runtime_budget**: assert runtime **Ã¢â€°Â¤ 5s** per **portfolio Ã¢â€°Â¤10 posizioni** e **10.000 scenari**.
- Se il run eccede limiti (posizioni/scenari), il test deve fallire o richiedere modalitÃƒÂ  scaling/approx dichiarata.

### Addendum v.T.11.7 Ã¢â‚¬â€ Nuovi test/gate

- **OPS_VALIDATOR_CRITICAL_BLOCKS**: un check CRITICAL FAIL deve restituire exit code 10 e `blocked=true`.
- **OPS_VALIDATOR_WARNING_NONBLOCK**: un check WARNING FAIL deve restituire exit code 2 e `blocked=false`.
- **F4-T_adaptive_fixed_fractional**: per `N_closed_trades<50` il sizing usa Adaptive Fixed Fractional (NORMAL=1.0, CAUTION=0.5, SHOCK=0.0); Kelly vietato.
- **F2-T_HMM_qualification_nonVIX**: ensemble upgrade consentito solo se HMM supera qualification su 3 famiglie shock (Ã¢â€°Â¥2/3 famiglie, valore netto vs XGBoost).
- **F2-T_correlation_breakdown_flag**: flag `CORRELATION_BREAKDOWN` si attiva quando z-score corr(SPY,TLT) < -2ÃÆ’; in presenza del flag si applica riduzione sizing/stop nuove posizioni short-vol.

#### Traceability Matrix Ã¢â‚¬â€ righe aggiuntive (v.T.11.7)
| Fase 0 (validator) | CLI validator + severity semantics | OPS_VALIDATOR_CRITICAL_BLOCKS, OPS_VALIDATOR_WARNING_NONBLOCK | Ops Gate |
| Fase 4 (risk) | Adaptive Fixed Fractional (pre-Kelly) | F4-T_adaptive_fixed_fractional | Model Gate |
| Fase 2 (hardening) | HMM qualification + Correlation detector | F2-T_HMM_qualification_nonVIX, F2-T_correlation_breakdown_flag | Model Gate |


**Allineamento criterio HMM (F2-T2):** lÃ¢â‚¬â„¢acceptance non ÃƒÂ¨ Ã¢â‚¬Å“lead time 1Ã¢â‚¬â€œ2g in >60% casiÃ¢â‚¬Â su campione generico, ma **qualification event-based**: HMM deve aggiungere valore in **Ã¢â€°Â¥ 2/3 famiglie di shock** (VIX-driven / correlation breakdown / credit-geopolitical) e non peggiorare falsi positivi. (Vedi `hmm_ensemble_qualification()` nel TECNICO.)


\
    ### Addendum v.T.11.13 Ã¢â‚¬â€ Gate 0 (Phase 0 Validator)

    - **P0-A1_dirs_present**: CRITICAL Ã¢â‚¬â€ cartelle `db/ data/ logs/ reports/ config/`
    - **P0-A2_lock_present**: CRITICAL Ã¢â‚¬â€ `requirements.lock`
    - **P0-A5_secrets_guard**: CRITICAL Ã¢â‚¬â€ no hardcoded secrets + env vars richieste
    - **P0-B2_schema_marker**: CRITICAL Ã¢â‚¬â€ `db/schema_applied.ok` presente
    - **P0-D1_ibkr_connectivity**: dev=WARNING; paper/live=CRITICAL Ã¢â‚¬â€ connessione IBKR (accountSummary ok)
    - **P0-D2_options_marketdata**: dev=WARNING; paper/live=CRITICAL Ã¢â‚¬â€ option bid/ask smoke test
    - **P0-E2_killswitch_config**: CRITICAL Ã¢â‚¬â€ kill-switch config presente
    - **OPS_VALIDATOR_CRITICAL_BLOCKS**: CRITICAL FAIL Ã¢â€ â€™ exit code 10
    - **OPS_VALIDATOR_WARNING_NONBLOCK**: WARNING FAIL Ã¢â€ â€™ exit code 2 (non blocca)

---

## ADDENDUM 2026-03-05 - DEMO DATA PIPELINE (deferred + LLM extraction)

### Fase 1 estesa
- ID: F1-T5
  - Nome: Capture pagine demo differite (subset titoli) con dedup/freshness.
  - Pass criteria: 0 duplicati persistiti con stessa fingerprint; skip su dato fresco.
- ID: F1-T6
  - Nome: Estrazione con Ollama qwen2.5 e output JSON schema-fisso.
  - Pass criteria: validatore deterministico green; retry limitato; fallback `needs_review`.
- ID: F1-T7
  - Nome: Build dataset test (CSV/Parquet) con provenance completa.
  - Pass criteria: dataset riproducibile da raw+index+versioni prompt/model.
- ID: F1-T8
  - Nome: Retention e controllo footprint disco.
  - Pass criteria: TTL/cap applicati; report audit con bytes, prune e duplicati evitati.

### Fase 2 estesa
- ID: F2-T5
  - Nome: Backtest su dataset demo pulito.
  - Pass criteria: runner eseguito su dataset validato, report metriche generato.
