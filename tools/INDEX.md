# Index — tools/

## File

| File | Descrizione |
|------|-------------|
| `add_step_tags_minimal.py` | Aggiunge idempotentemente un tag step-comment in cima ai file di implementazione target |
| `append_registro_reconcile_step_index.py` | Appende un'entry di riconciliazione step-index nel registro `.canonici/REGISTRO_INTEGRITA.md` |
| `apply_patch.py` | Applica un PATCH_*.zip al repo root ed esegue opzionalmente auto-reconcile dell'indice |
| `apply_qopz_002_cleanup.py` | Patch QOPZ-002: sposta PATCH_NOTES obsolete e mette in quarantena script IBKR legacy |
| `apply_qopz_004_ui.py` | Patch QOPZ-004: rimuove `ui/node_modules` stale dalla snapshot del repo |
| `certify_steps.py` | Certifica la coerenza tra `.qoaistate.json` e `.step_index.json`, riportando eventuali drift |
| `d2_13_apply.py` | Applica lo step D2.13: aggiorna state con ACK/timeout taxonomy e ricostruisce il manifest |
| `d2_14_apply.py` | Applica lo step D2.14: aggiorna state, docs e registro integrità per il completamento di D2.14 |
| `f1_t1_ingest_spy.py` | Runner F1-T1: ingestione OHLCV giornaliero in DuckDB da CSV, con report di completezza |
| `f1_t2_compute_ivr.py` | Runner F1-T2: calcola IV Rank per i ticker configurati da CSV storico e produce report JSON/MD |
| `f1_t3_check_options_chain.py` | Runner F1-T3: quality check della catena opzioni su CSV campionato (offline) |
| `f1_t4_db_integrity.py` | Runner F1-T4: check integrità DuckDB (PK, FK, timestamp, performance) con opzione seed sintetico |
| `f2_t1_train_regime_classifier.py` | Runner F2-T1: addestra il classificatore di regime (Gaussian NB + Platt) su dati storici offline |
| `f2_t2_fit_hmm_rolling.py` | Runner F2-T2: fit HMM rolling e confronto con baseline XGB, produce report JSON |
| `f2_t3_finalize_state.py` | Runner F2-T3: finalizza lo stato planner portando next_step oltre F2-T3 (noop se già avanzato) |
| `f2_t3_regime_risk_scalar.py` | Runner F2-T3 (risk scalar): calcola la serie di risk scalar da probabilità HMM+classifier |
| `f2_t4_wfa_bull_put.py` | Runner F2-T4: Walk-Forward Analysis Bull Put con output JSON/MD dei fold IS/OOS |
| `f3_t1_ibkr_connectivity.py` | Runner F3-T1: verifica connettività TCP verso TWS/IB Gateway con check opzionale ib_insync |
| `f3_t2_ibkr_combo_smoke.py` | Runner F3-T2: smoke test ordine combo Bull Put su IBKR paper (human-confirmed, con simulate fill) |
| `f5_t1_microstructure.py` | Runner F5-T1: calcola feature microstrutturali da input CLI (volume delta, OI velocity, skew) |
| `f5_t2_twap_execution.py` | Runner F5-T2: costruisce il piano di execution TWAP (slices, intervalli) da bid/ask e quantity |
| `f5_t3_drawdown_control.py` | Runner F5-T3: valuta la policy di drawdown control su serie equity e livelli di regime |
| `f6_t1_paper_metrics.py` | Runner F6-T1: calcola le metriche paper trading (Sharpe, MaxDD, WinRate, slippage) per la fase GO/NO-GO |
| `f6_t2_go_nogo_pack.py` | Runner F6-T2: produce il pacchetto GO/NO-GO con metriche paper e gate di qualificazione live |
| `f6_t3_stress_live.py` | Runner F6-T3: esegue la stress suite pre-live (`execution.stress_live`) con dati sintetici |
| `fix_make_repo_zip_bat.py` | Ripristina/verifica il contenuto canonico di `make_repo_zip.bat` (bytes attesi embedded in base64) |
| `fix_portable_snapshot.py` | Applica la policy `.gitattributes` (no text normalization) e la whitelist `.gitignore` |
| `hf_progress_tracking_alignment.py` | Inserisce idempotentemente F1-T2 nella lista steps_completed del state file |
| `hf_release_plan_go_nogo.py` | Aggiorna la sezione GO/NO-GO in `.canonici/04_APPENDICI.md` leggendo `release_plan_go_nogo.json` |
| `opz_env_setup.py` | Setup ambiente Python Windows: crea il venv scelto (`--venv-name`, default `.venv`) e installa i requirements (idempotente) |
| `opz_protected_validate.py` | Validazione pre-rilascio in ambiente protetto isolato (`.venv_protected`): repo sync, planner guard, test core, VM dry-run opzionale e gates |
| `opz_f3_t1_runner.py` | Runner F3-T1 full (logica di connettività IBKR con retry e report strutturato) |
| `opz_f3_t2_runner.py` | Runner F3-T2 full (smoke test combo IBKR con ciclo send/modify/cancel/fill e P&L simulato) |
| `opz_state_normalize.py` | Normalizza lo schema di `.qoaistate.json`: unifica progress, migra chiavi legacy root |
| `opz_step_ctl.py` | Controllo step: block/unblock/set-next su `.qoaistate.json` con validazione e timestamp |
| `planner_guard.py` | Guard del planner: verifica scope dei file modificati rispetto allo step attivo, lock/clear step |
| `rebuild_manifest.py` | Ricostruisce il file `.canonici/MANIFEST.txt` (SHA-256 + size) per tutti i file del repo |
| `reconcile_step_index.py` | Calcola il `step_index` derivato dallo state (lista step completati, next_step, metadati) |
| `release_status.py` | Mostra lo stato dei milestone di release leggendo `.step_index.json` e `release_plan_go_nogo.json` |
| `run_gates.py` | Esegue in sequenza i gate pre-commit (guard scope, manifest, certify) con il Python del venv |
| `set_broker_port.py` | Aggiorna la porta broker nella sezione `[broker]` del file TOML di configurazione profilo |
| `verify_manifest.py` | Verifica il manifest `.canonici/MANIFEST.txt` confrontando SHA-256 e dimensioni file su disco |

---

## Tassonomia

### Planner / scope guard (strumenti di controllo del piano)
- `planner_guard.py` — guard scope step attivo, lock/clear
- `run_gates.py` — pipeline gate pre-commit (guard + manifest + certify)
- `opz_step_ctl.py` — controllo manuale step (block/unblock/set-next)
- `reconcile_step_index.py` — calcolo derivato step_index da state
- `certify_steps.py` — verifica drift state ↔ step_index
- `hf_progress_tracking_alignment.py` — inserimento idempotente step in state

### Manifest / integrità repo
- `rebuild_manifest.py` — ricostruzione MANIFEST.txt (SHA-256)
- `verify_manifest.py` — verifica manifest su disco
- `append_registro_reconcile_step_index.py` — entry registro integrità

### Setup / ambiente / patch
- `opz_env_setup.py` — setup venv + requirements (Windows)
- `opz_protected_validate.py` — pre-release validation in isolated protected venv
- `apply_patch.py` — applicazione PATCH_*.zip
- `apply_qopz_002_cleanup.py` — cleanup script legacy e PATCH_NOTES
- `apply_qopz_004_ui.py` — rimozione node_modules stale
- `fix_make_repo_zip_bat.py` — ripristino make_repo_zip.bat canonico
- `fix_portable_snapshot.py` — policy gitattributes no-text-normalization
- `add_step_tags_minimal.py` — aggiunta tag step nei file sorgente

### Step apply (applica singoli step di progresso)
- `d2_13_apply.py` — applica D2.13 (ACK/timeout taxonomy)
- `d2_14_apply.py` — applica D2.14 (docs e registro)
- `f2_t3_finalize_state.py` — finalizza stato F2-T3

### Runner milestones F1 (data pipeline)
- `f1_t1_ingest_spy.py` — ingestione OHLCV → DuckDB
- `f1_t2_compute_ivr.py` — calcolo IV Rank
- `f1_t3_check_options_chain.py` — quality check catena opzioni
- `f1_t4_db_integrity.py` — check integrità DuckDB

### Runner milestones F2 (regime)
- `f2_t1_train_regime_classifier.py` — training classificatore regime
- `f2_t2_fit_hmm_rolling.py` — fit HMM rolling + baseline
- `f2_t3_regime_risk_scalar.py` — calcolo risk scalar
- `f2_t4_wfa_bull_put.py` — WFA Bull Put IS/OOS

### Runner milestones F3 (IBKR paper)
- `f3_t1_ibkr_connectivity.py` — check connettività TCP/ib_insync
- `f3_t2_ibkr_combo_smoke.py` — smoke test ordine combo paper
- `opz_f3_t1_runner.py` — runner F3-T1 completo
- `opz_f3_t2_runner.py` — runner F3-T2 completo

### Runner milestones F5 (microstructure / execution)
- `f5_t1_microstructure.py` — feature microstrutturali
- `f5_t2_twap_execution.py` — piano TWAP execution
- `f5_t3_drawdown_control.py` — policy drawdown control

### Runner milestones F6 (GO/NO-GO)
- `f6_t1_paper_metrics.py` — metriche paper trading
- `f6_t2_go_nogo_pack.py` — pacchetto GO/NO-GO
- `f6_t3_stress_live.py` — stress suite pre-live

### Release / stato progetto
- `release_status.py` — stato milestone di release
- `hf_release_plan_go_nogo.py` — aggiornamento appendice GO/NO-GO
- `opz_state_normalize.py` — normalizzazione schema state
- `set_broker_port.py` — aggiornamento porta broker in TOML
