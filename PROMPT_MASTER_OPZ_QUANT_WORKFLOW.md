# PROMPT MASTER OPZ QUANT - WORKFLOW GENERALE (TUTTE LE FASI)

## CONTESTO
In questa chat allego uno ZIP della repo: lo ZIP e' l'unica fonte di verita'.
Usa solo file nello ZIP + output comandi forniti in chat.
Niente web, niente memoria esterna, niente assunzioni non verificabili in repo.

---

## 1) OBIETTIVO
Supportare sviluppo, hardening, test, rilascio e monitoraggio su qualsiasi fase del progetto,
con avanzamento tracciato e enforcement planner.

Valido per:
- Fase 0..6
- Step D2.* / F*-T*
- Milestone secondarie R0..R5
- Target primari PT1_MICRO..PT4_ADVANCED

---

## 2) VINCOLI NON NEGOZIABILI
- Execution sempre human-confirmed (mai autopilota).
- Windows-first (PowerShell), no dipendenze Linux-only.
- Patch minime, idempotenti, verificabili.
- Nessun editing manuale delle sorgenti di stato quando esiste tool dedicato.
- Demo-first per data tuning: usare dati demo differiti e set titoli limitato finch? non si passa a realtime.

---

## 3) PLANNER ENFORCEMENT (HARD RULE)
Sorgenti autoritative:
- `planner/master_plan.json`
- `planner/active_step.json`
- `.qoaistate.json`

Regole:
1. L'agente opera solo sullo step attivo.
2. Se modifiche fuori scope step => STOP.
3. Nessun step marked done senza evidenze (test/gate/report).

Comandi obbligatori:
- `py scripts\planner_status.py --format md`
- `py tools\planner_guard.py check --check-target index`
- `py tools\run_gates.py --skip-manifest --skip-certify`

---

## 4) STANDARD ESECUZIONE
- Ambiente: PowerShell.
- Python: usare `py`.
- Venv: `.venv` se presente.
- Evitare refactor cosmetici non necessari allo step.
- Evitare rilancio comandi inutilmente se gia' verdi.

---



---

## 4B) DATA PIPELINE DEMO (F1-T5..F2-T5)
Regole operative obbligatorie:
- Salvare raw solo se contenuto cambia (`raw-on-change`) con fingerprint SHA256.
- Evitare duplicati con indice locale (`source,symbol,page_type,fingerprint` univoco).
- Applicare finestra freschezza (default 60 min) e skip capture se dato recente gi? presente.
- Applicare retention: TTL + cap dimensione disco con prune controllato.
- Usare LLM (Ollama qwen2.5) solo per estrazione, sempre dietro validatore deterministico.
- Output estrazione solo JSON schema-fisso; retry limitato; fallback `needs_review`.
- Dataset finale pulito e riproducibile (CSV/Parquet) per backtest.

Comandi standard pipeline:
- `py scripts\capture_pages.py`
- `py scripts\extract_with_ollama.py`
- `py scripts\build_test_dataset.py`
- `py scripts\run_backtest.py`

## 5) PROTOCOLLO RISPOSTA
Ogni risposta deve includere:
1. Stato sintetico (branch, next_step, planner status, milestone)
2. Decisione operativa (prossimo step + motivo)
3. Patch proposta (file toccati)
4. Comandi PowerShell copy-paste per apply/verify/gate/status
5. Se il tema ? avanzamento: includere anche `py scripts\advancement_matrix.py --format md`

---

## 6) WORKFLOW OPERATIVO (INIZIO SESSIONE)
1. `git rev-parse --abbrev-ref HEAD`
2. `git status -sb`
3. `py scripts\planner_status.py --format md`
3b. `py scripts\advancement_matrix.py --format md`
4. `py tools\release_status.py --format md`
5. `py tools\planner_guard.py status --format line`
6. `py tools\planner_guard.py check --check-target index`

Se check planner fallisce: non sviluppare finche' lock/scope non e' coerente.

---

## 7) WORKFLOW OPERATIVO (DURANTE SVILUPPO)
1. Implementa solo scope consentito dallo step attivo.
2. Esegui test mirati.
3. Esegui gate:
   - `py tools\planner_guard.py check --check-target index`
   - `py tools\run_gates.py --skip-manifest --skip-certify`

---

## 8) WORKFLOW OPERATIVO (FINE SESSIONE)
1. `py scripts\planner_status.py --format line`
2. `py tools\release_status.py --format md`
3. Aggiorna stato step con tool (no edit manuale stato)
4. `git status --short`
5. Commit/push solo con gate verdi o blocchi esplicitati

---

## 9) SORGENTI AUTORITATIVE
- Piano planner: `planner/master_plan.json`
- Lock attivo: `planner/active_step.json`
- Stato runtime: `.qoaistate.json`, `.step_index.json`
- Stato rilascio: `config/release_plan_go_nogo.json` + `py tools\release_status.py --format md`
- Canone tecnico/operativo: `.canonici/*`

In caso mismatch tra documenti e tools: prevalgono le sorgenti macchina e i gate.

---

## 10) OUTPUT ZIP / PATCH (SE RICHIESTI)
Naming consigliato:
- Patch: `PATCH_OPZ_QUANT_<id>_<desc>.zip`
- Snapshot: `REPO_OPZ_QUANT_<yyyymmdd_hhmm>.zip`

Ogni patch deve essere applicabile e verificabile in modo ripetibile.

---

## 11) AVVIO RAPIDO (PRIMO PASSO)
1. Leggi ZIP
2. Emetti stato sintetico
3. Proponi prossimo step coerente con planner
4. Implementa e valida con planner guard + gates
