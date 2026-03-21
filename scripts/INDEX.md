# Index — scripts/

## File

| File | Descrizione |
|------|-------------|
| `advancement_matrix.py` | Costruisce la matrice di avanzamento milestone leggendo master_plan.json, step_index e canonical tasks |
| `build_test_dataset.py` | Assembla il dataset di test (demo pipeline) da raw captures estratte, con dedup e fingerprint SHA-256 |
| `build_tesseract_json.py` | Converte testi OCR Tesseract da `data/ibkr_screens/ocr_txt/` in un JSON strutturato con simboli e tab |
| `capture_pages.py` | Indicizza e gestisce i file raw catturati (JSON/HTML/TXT) nella demo pipeline, applicando freshness e dedup |
| `db_integrity.py` | Libreria F1-T4: check integrità DuckDB (PK unici, FK, timestamp, performance join su dati sintetici) |
| `demo_pipeline_lib.py` | Libreria condivisa della demo pipeline: path, hashing SHA-256, I/O JSON, helper DuckDB |
| `events_calendar.py` | Recupera eventi societari (earnings, dividendi) via yfinance e applica regole di blocco/flag per trade |
| `extract_with_ollama.py` | Estrae dati finanziari strutturati (bid/ask/IV) da catture raw usando Ollama come LLM locale |
| `fetch_iv_history.py` | Scarica la storia IV (ATM implied volatility) per una lista di simboli via yfinance e salva in JSON |
| `generate_briefing.py` | Genera un bollettino audio MP3 mattutino (regime, equity, opportunità) via edge-tts e lo invia su Telegram |
| `git_eol_policy.py` | Verifica e applica la policy EOL git (autocrlf, safecrlf, eol) al repo locale |
| `healthcheck.py` | Runner di healthcheck (D2.19+): esegue check di stabilità locale con exit code espliciti e output JSON/MD |
| `hmm_regime.py` | Implementazione Pure-Python di un HMM gaussiano (Baum-Welch) per classificazione regime NORMAL/CAUTION/SHOCK |
| `ibkr_demo_fetch_inbox.py` | Recupera l'universo dei simboli da IBKR settings e crea il dataset demo pipeline per la sessione corrente |
| `ibkr_f3_t1_check.py` | Entry-point convenience (wrapper) per il check di connettività IBKR F3-T1 |
| `ibkr_ocr_paddle_extract.py` | Estrae testo e simboli da screenshot IBKR usando PaddleOCR (CPU-only, Windows-safe) |
| `ibkr_screen_to_inbox.py` | Normalizza e importa dati da capture CSV/JSON di schermate IBKR nella demo pipeline inbox |
| `ibkr_uia_extract.py` | Estrae dati dalle finestre TWS/IBKR tramite UI Automation (pywinauto) senza OCR |
| `ibkr_vision_extract_ollama.py` | Estrae dati finanziari da screenshot IBKR tramite Ollama vision (multimodale, base64) |
| `init_db.py` | Inizializza il file DuckDB e scrive il marker `schema_applied.ok` leggendo il config TOML/JSON |
| `ivr.py` | Libreria IV Rank: calcola IV Rank (0–100) su una finestra lookback da CSV di storia IV |
| `market_data_ingest.py` | Libreria F1-T1: ingestione OHLCV giornaliero in DuckDB con report di completezza |
| `metrics.py` | Libreria metriche: equity curve, max drawdown, win rate, Sharpe annualizzato |
| `microstructure_features.py` | Calcola feature microstrutturali (volume delta, OI velocity, IV curvature) per il segnale di execution |
| `opz_f3_t1_run.py` | Entry-point (wrapper script) per il runner F3-T1 IBKR connectivity |
| `opz_f3_t2_run.py` | Entry-point (wrapper script) per il runner F3-T2 IBKR combo smoke test |
| `opz_process_registry.py` | Registro persistente dei processi agente (`logs/codex_process_registry.json`): add/remove/list |
| `options_chain_quality.py` | Libreria F1-T3: quality check della catena opzioni (bid<=ask, delta range, IV range, put-call parity) |
| `planner_status.py` | Mostra lo stato corrente del planner (milestone, step attivo, next step) da master_plan.json |
| `progress_report.py` | Reporter di avanzamento (D2.24+): view per fase (F1–F6) e track D2, output JSON/MD/line |
| `project_status.py` | Aggregatore di stato progetto (D2.41): git sync + avanzamento fasi + stato planner in un unico payload |
| `quick_audit.py` | Audit rapido AST+regex sui moduli critici: rileva bare except, datetime naive, mancanza Kelly gate |
| `reconcile_execution.py` | Avvia la riconciliazione del DB di execution (chiama `execution.reconcile`) e stampa il risultato JSON |
| `regime_classifier.py` | Classificatore di regime (NORMAL/CAUTION/SHOCK) tramite Gaussian Naive Bayes + Platt scaling |
| `regime_risk_scaler.py` | Combina probabilità HMM+classifier in un risk scalar [0.25–1.0] con isteresi e EMA smoothing |
| `repo_sync_status.py` | Verifica l'allineamento del branch locale con il remote (ahead/behind) via git CLI |
| `run_backtest.py` | Esegue un backtest semplificato sui dataset demo pipeline usando le metriche di `metrics.py` |
| `sanitize_ibkr_settings.py` | Oscura campi sensibili (account, password, token) da file XML di configurazione IBKR |
| `session_runner.py` | Orchestratore sessioni morning/EOD: chiama API regime, IV history, events, universe scan, briefing |
| `sitecustomize.py` | Fix Windows: patcha `tempfile.mkdtemp` per evitare errori di permesso su mode 0o700 |
| `submit_order.py` | CLI per inviare un ordine tramite il boundary D2 di execution, con preflight dipendenze e gate0 broker |
| `test_generator_agent.py` | Mappa file modificati ai moduli di test corrispondenti e può scaffoldare stub di test mancanti |
| `wfa_bull_put.py` | Walk-Forward Analysis per strategia Bull Put: 3y IS / 1y OOS, metriche Sharpe/DD/WinRate |
| `wfa_iron_condor.py` | Walk-Forward Analysis per strategia Iron Condor: struttura analoga a wfa_bull_put con parametri IC |

---

## Tassonomia

### Planner / stato progetto
- `advancement_matrix.py` — matrice milestone da master_plan e step_index
- `planner_status.py` — stato step attivo e milestone
- `progress_report.py` — avanzamento per fase (F1–F6) e track D2
- `project_status.py` — aggregatore git + fasi + planner
- `repo_sync_status.py` — allineamento branch locale/remote

### Gate / audit / qualità
- `quick_audit.py` — audit AST+regex su moduli critici
- `git_eol_policy.py` — verifica/applica policy EOL git
- `healthcheck.py` — healthcheck locale con exit codes espliciti
- `test_generator_agent.py` — mappa file→test e scaffold stub

### Data ingest / market data
- `market_data_ingest.py` — OHLCV giornaliero → DuckDB (F1-T1)
- `fetch_iv_history.py` — storia IV ATM da yfinance → JSON
- `events_calendar.py` — earnings/dividendi da yfinance con regole blocco
- `ivr.py` — calcolo IV Rank su finestra lookback
- `db_integrity.py` — check integrità DuckDB (F1-T4)
- `init_db.py` — inizializzazione file DuckDB + marker schema
- `options_chain_quality.py` — quality check catena opzioni (F1-T3)

### Regime / strategia
- `hmm_regime.py` — HMM gaussiano Pure-Python per classificazione regime
- `regime_classifier.py` — Gaussian NB + Platt scaling → NORMAL/CAUTION/SHOCK
- `regime_risk_scaler.py` — risk scalar combinato HMM+classifier con isteresi
- `microstructure_features.py` — feature microstrutturali (volume delta, OI velocity, IV curvature)
- `wfa_bull_put.py` — WFA Bull Put spread
- `wfa_iron_condor.py` — WFA Iron Condor
- `metrics.py` — libreria metriche (Sharpe, MaxDD, WinRate, equity curve)

### Execution / ordini
- `submit_order.py` — CLI invio ordine via boundary D2
- `reconcile_execution.py` — riconciliazione DB execution

### IBKR / OCR / demo pipeline
- `demo_pipeline_lib.py` — libreria condivisa demo pipeline (path, hash, I/O)
- `capture_pages.py` — gestione file raw nella demo pipeline
- `build_test_dataset.py` — costruzione dataset di test da captures
- `extract_with_ollama.py` — estrazione LLM da raw captures (Ollama)
- `ibkr_demo_fetch_inbox.py` — fetch universe IBKR → dataset demo
- `ibkr_screen_to_inbox.py` — import captures CSV/JSON → inbox demo
- `ibkr_ocr_paddle_extract.py` — OCR PaddleOCR da screenshot IBKR
- `ibkr_uia_extract.py` — estrazione UI Automation da TWS/IBKR
- `ibkr_vision_extract_ollama.py` — estrazione vision multimodale Ollama da screenshot IBKR
- `build_tesseract_json.py` — conversione testi Tesseract OCR → JSON strutturato
- `sanitize_ibkr_settings.py` — oscuramento campi sensibili in config XML IBKR
- `ibkr_f3_t1_check.py` — wrapper CLI per check connettività IBKR (F3-T1)

### Session / notifiche
- `session_runner.py` — orchestratore sessioni morning/EOD
- `generate_briefing.py` — bollettino audio MP3 + Telegram
- `telegram_command_bot.py` — bot Telegram per comandi operativi via polling
- `opz_f3_t1_run.py` — entry-point runner F3-T1
- `opz_f3_t2_run.py` — entry-point runner F3-T2

### Ops / utilità
- `opz_process_registry.py` — registro processi agente
- `run_backtest.py` — backtest semplificato su dataset demo
- `sitecustomize.py` — fix Windows tempfile.mkdtemp (permessi)
