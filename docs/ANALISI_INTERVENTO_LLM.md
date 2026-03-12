# Analisi di intervento — stato avanzamento e strategia LLM-first

_Data: 2026-02-27_

## 1) Obiettivo e metodo

Questa analisi valuta:
1. lo stato reale del progetto rispetto al piano canonico (`.canonici/*`);
2. i gap tecnici e operativi che bloccano la progressione;
3. dove conviene sostituire (in parte) codice/artefatti statici con prompt LLM strutturati, per ridurre complessità e aumentare velocità.

Approccio usato:
- baseline normativa da `00_MASTER`, `01_TECNICO`, `02_TEST`, `03_SETUP`;
- baseline operativa da `.qoaistate.json`, test suite e validator;
- classificazione interventi in **tenere in codice** vs **spostare su LLM**.

---

## 2) Lettura del piano complessivo (canonico)

### 2.1 Architettura del piano
Il piano canonico prevede una progressione per fasi:
- **Phase 0**: readiness/validator/Gate 0 (obbligatorio, blocca su CRITICAL);
- **Fase 1-2**: pipeline dati + regime detection;
- **Fase 3**: execution/paper boundary;
- **Fase 4**: scoring + sizing;
- **Fase 5**: microstructure/stress;
- **Fase 6**: paper prolungato e GO/NO-GO finale.

### 2.2 Vincolo di governance
Il framework di controllo richiede che la certificazione release passi da:
- implementazione controlli hard;
- coerenza integrità/manifest;
- assenza di violazioni di dipendenze HARD/CERT.

---

## 3) Stato effettivo del repository

## 3.1 Progresso dichiarato vs implementato
Da `.qoaistate.json` il progetto dichiara completati vari step Domain 2 (D2.3A, D2.5, D2.6, D2.7, D2.8, D2.9, D2.15, D2.16) e una tranche Phase 4 (`F4.1`, `F4.1.HF1`), con `next_step = D2.17`.

### 3.2 Evidenza test disponibile
La suite presente copre soprattutto:
- **Execution (D2)**: adapter boundary, event trail, ACK taxonomy, reducer/state integration, smart ladder, reconcile/outcome;
- **Scoring/Sizing (F4)**: score composito + Kelly con bound.

Mancano invece test espliciti di:
- Fase 1 (pipeline dati quality);
- Fase 2 (regime/anti-leakage OOS come blocco reale di pipeline);
- Fase 5-6 (stress e go-live gates completi).

### 3.3 Risultati runtime attuali (oggi)
Eseguendo i check locali:
- `python -m unittest -v`: **1 failure** su caso paper submit (atteso `REJECTED_BROKER_UNAVAILABLE`, osservato `REJECTED_ENV` quando manca `duckdb`);
- `python validator.py --profile dev --config config/dev.toml`: **crash** su `dt.UTC` (compatibilità runtime Python, tipicamente 3.10).

Conclusione: lo stato è **parzialmente avanzato in Domain 2/F4**, ma **non pronto a certificazione Gate 0** su ambiente non allineato.

---

## 4) Gap prioritari (rigorosi, ordinati per impatto)

## P0 — Bloccanti immediati
1. **Validator non portabile su runtime Python eterogenei** (uso `dt.UTC`).
2. **Fragilità preflight dipendenze in `submit_order`**: il test paper boundary viene condizionato da una dipendenza core locale (`duckdb`) prima della semantica broker-unavailable.

## P1 — Rischio architetturale
3. **Sovrapposizione documentale**: molte policy sono ripetute tra canonici/addendum/registro, con costo alto di mantenimento manuale.
4. **Copertura traceability incompleta fuori da D2/F4**: manca catena test->gate per F1/F2/F5/F6 in CI eseguibile.

## P2 — Efficienza sviluppo
5. **Overhead su artefatti statici** (report/appendici/note): lavoro ripetitivo adatto ad automazione LLM guidata da template e check deterministici.

---

## 5) Strategia di alleggerimento: cosa lasciare in codice vs cosa spostare su prompt LLM

## 5.1 Da mantenere deterministicamente in codice
Non va delegato a LLM:
- state machine ordini, reducer, invarianti reconcile;
- policy di exit code e severity del validator;
- normalizzazione eventi broker e idempotenza;
- calcoli di sizing/risk usati in produzione.

Regola: tutto ciò che modifica stato, capitale, execution path o criteri di gate deve restare testabile deterministicamente.

## 5.2 Da spostare (parzialmente) a LLM
Conviene usare prompt strutturati per:
- **Generazione documentazione operativa** (runbook, report narrativi, changelog ragionato);
- **Bozze patch-note e mapping traceability** da evidenze machine-readable;
- **Prioritizzazione backlog** da output test/validator;
- **Scaffold di test-case** a partire da canonical IDs.

Risultato atteso: meno codice “colla”, meno tempo su redazione manuale, più throughput sulle parti core.

---

## 6) Prompt kit proposto (specifico per questo repo)

## Prompt A — Traceability auto-draft
**Input**: `.canonici/02_TEST.md`, elenco `tests/test_*.py`, ultimo `.qoaistate.json`.
**Output**: tabella “Gate -> test evidence -> stato (OK/PARTIAL/MISSING)”.

Template sintetico:
> "Leggi i canonical gate in `.canonici/02_TEST.md` e mappa i test presenti in `tests/`.
> Produci tabella con colonne: Gate, Test IDs attesi, Test files trovati, Coverage, Gap, Next action.
> Non inventare test inesistenti. Evidenzia mismatch tra stato dichiarato in `.qoaistate.json` e copertura reale."

## Prompt B — Failure triage operativo
**Input**: output `python -m unittest -v`, output validator, file coinvolti.
**Output**: top-5 fix ordinati per impatto, con stima effort e rischio regressioni.

## Prompt C — Patch-note compliance
**Input**: `git diff`, `.canonici/REGISTRO_INTEGRITA.md`, `PATCH_NOTES.md`.
**Output**: bozza patch notes coerente con registro integrità, con sezione “breaking/non-breaking”.

## Prompt D — Test scaffold canonico
**Input**: un gate mancante (es. F2-T_leakage_guard).
**Output**: skeleton test file + casi minimi + fixture contract, senza implementare logica di business.

---

## 7) Piano operativo di intervento (2 sprint brevi)

## Sprint 1 (stabilizzazione)
1. Rendere validator compatibile con Python 3.10/3.11.
2. Separare nel submit CLI il ramo `paper/live` dal preflight non necessario al caso broker-unavailable.
3. Ripristinare baseline verde su suite D2/F4.
4. Introdurre un comando unico di health check locale (validator + unit test).

## Sprint 2 (LLM-first enablement)
5. Aggiungere cartella `prompts/` con Prompt A/B/C/D versionati.
6. Generare automaticamente report traceability e patch-note draft in CI (artefatti non bloccanti).
7. Misurare KPI per 2 settimane:
   - lead time da issue a PR,
   - % file documentali toccati manualmente,
   - tasso regressioni test.

### 7.1 TODO esecutiva (ordine rigoroso)

1. **Fix validator runtime compatibility**
   - Azione: sostituire `dt.UTC` con fallback compatibile 3.10/3.11.
   - Done quando: `validator.py --profile dev` ritorna exit code coerente (0/2/10) senza crash.

2. **Fix submit CLI boundary semantics (paper/live)**
   - Azione: nel ramo `paper/live`, non bloccare prima sulla dipendenza `duckdb` quando il comportamento atteso è `REJECTED_BROKER_UNAVAILABLE`.
   - Done quando: `tests/test_d2_11_adapter_boundary.py` green sul caso paper reject.

3. **Consolidare baseline test minima di avanzamento**
   - Azione: definire una test suite minima obbligatoria D2/F4 (smoke + invariants) per ogni patch.
   - Done quando: comando unico di healthcheck fallisce solo su regressioni reali.

4. **Versionare prompt operativi in repo (`prompts/`)**
   - Azione: introdurre Prompt A/B/C/D con input/output contract e policy “no invention”.
   - Done quando: i report generati da prompt sono riproducibili e verificabili da file sorgente.

5. **Automatizzare output documentali non bloccanti in CI**
   - Azione: generare draft traceability + patch notes come artefatti CI, senza impattare gate runtime.
   - Done quando: riduzione document edits manuali misurabile su 2 settimane.

### 7.2 Benefici progressivi attesi (step-by-step)

- **Dopo TODO #1**
  - Beneficio: Gate 0 torna eseguibile su ambienti eterogenei (meno falsi blocchi dovuti alla versione Python).

- **Dopo TODO #2**
  - Beneficio: semantica execution boundary coerente con policy canonica; test D2 più affidabili come segnale di qualità.

- **Dopo TODO #3**
  - Beneficio: ciclo patch più veloce (feedback breve, regressioni intercettate prima, meno debugging tardivo).

- **Dopo TODO #4**
  - Beneficio: riduzione lavoro ripetitivo su analisi/traceability; maggiore uniformità nei report.

- **Dopo TODO #5**
  - Beneficio: throughput più alto del team su feature core (execution/risk) perché la documentazione “colla” diventa semi-automatica.

### 7.3 Piano sintetico per settimana

| Settimana | Deliverable | KPI primario |
|---|---|---|
| W1 | TODO #1 + #2 completati | Validator dev non crasha; test boundary paper green |
| W2 | TODO #3 completato | baseline D2/F4 stabile (pass rate alto e costante) |
| W3 | TODO #4 completato | primi report LLM riproducibili da artefatti repo |
| W4 | TODO #5 completato | riduzione editing manuale doc e lead time patch |

---

## 8) KPI e criteri di successo

Successo tecnico:
- validator dev torna a exit policy prevista;
- suite D2/F4 completamente green su ambiente target;
- nessuna riduzione di copertura sui moduli execution/risk.

Successo di processo:
- almeno 30-40% riduzione tempo su attività documentali ripetitive;
- almeno 20% riduzione ciclo medio patch minori;
- nessun aumento di incidenti su gate critici.

---

## 9) Decisione raccomandata

Raccomandazione: **approccio ibrido, non full-LLM**.
- Core execution/risk/gate logic resta deterministic code.
- Tutta la “knowledge glue” (traceability narrative, patch note, backlog triage, scaffolding test) passa a prompt LLM standardizzati e versionati.

Questo massimizza velocità e feature throughput senza compromettere auditabilità e sicurezza operativa.


---

## 10) Integrazione della TODO nel piano implementativo del progetto

Per integrare la TODO nel piano complessivo, va trattata come **workstream trasversale** con ancoraggi espliciti a Gate/Fasi canoniche.

### 10.1 Mappatura TODO -> Fase/Gate canonico

| TODO | Fase/Gate primario | Dipendenze | Output richiesto |
|---|---|---|---|
| #1 Validator compatibility | **Phase 0 / Gate 0** | nessuna | validator eseguibile su Py 3.10/3.11, exit policy stabile |
| #2 Submit boundary semantics | **Fase 3 / Execution Gate** | #1 consigliata | semantica paper/live coerente (`REJECTED_BROKER_UNAVAILABLE`) |
| #3 Baseline test minima D2/F4 | **Fase 3 + Fase 4** | #1-#2 | suite minima obbligatoria in CI locale |
| #4 Prompt versionati (`prompts/`) | **Ops Enablement (cross-phase)** | #3 | prompt con contract input/output e policy anti-allucinazione |
| #5 Artefatti CI documentali | **Release/Ops Gate (non-bloccante)** | #4 | draft traceability/patch note generati automaticamente |

### 10.2 Inserimento nel backlog ufficiale (struttura consigliata)

Creare in backlog 3 epic, con issue numerate:

- **EPIC-A Stabilizzazione Gate**
  - A1 = TODO #1
  - A2 = TODO #2
  - A3 = TODO #3

- **EPIC-B LLM Enablement controllato**
  - B1 = TODO #4
  - B2 = TODO #5

- **EPIC-C Misurazione e adozione**
  - C1 = KPI setup
  - C2 = review a 2 settimane

### 10.3 Criteri di avanzamento nel piano (Definition of Progress)

Ogni TODO entra nel piano solo se ha:
1. **owner** (unico responsabile);
2. **evidenza tecnica** (test/report/command output);
3. **criterio di uscita** (DoD misurabile);
4. **impatto gate** (bloccante/non-bloccante).

Regola pratica:
- TODO #1-#3 = **bloccanti di stabilizzazione** (priorità massima);
- TODO #4-#5 = **acceleratori** (priorità alta ma non bloccante runtime).

### 10.4 Sequenza di integrazione nel ciclo release

- **Release N (hardening)**: chiudere TODO #1-#3.
- **Release N+1 (enablement)**: introdurre TODO #4-#5.
- **Release N+2 (ottimizzazione)**: tarare KPI e consolidare processi.

In questo modo, il piano evita di mescolare fix critici e automazione documentale nella stessa finestra di rischio.

### 10.5 Benefici progressivi nel piano ufficiale

- Dopo **Release N**: affidabilità tecnica (Gate 0/Execution più robusti).
- Dopo **Release N+1**: riduzione lavoro manuale e maggiore velocità di delivery.
- Dopo **Release N+2**: stabilizzazione del modello operativo LLM-assisted con metriche reali.

### 10.6 Aggiornamento stato progetto (come tracciarlo)

Aggiornare a ogni merge:
- `.qoaistate.json` -> nuovo `step` con riferimento a TODO/EPIC;
- `PATCH_NOTES.md` -> impatto operativo + rischio regressione;
- (opzionale) `docs/TRACEABILITY_PHASE0.md` -> solo se varia la semantica Gate 0.

Così la TODO non resta “documento parallelo”, ma diventa parte della governance esecutiva del progetto.

### 10.7 Addendum dati market feed (allineamento 2026-03-05)

Decisione operativa aggiornata:
1. **Fase Test (obbligatoria adesso)**: usare `IBKR demo` (dataset differito, numero titoli limitato) per validare pipeline e robustezza.
2. **Fase Valutazione fonti (prima del live)**: confronto strutturato tra tre canali:
   - API realtime a pagamento;
   - fonti gratuite/differite;
   - acquisizione da sito reale senza canone API.
3. **Fase Operativa**: attivare la fonte vincente senza riscrivere la pipeline (switch tramite adapter provider).

Vincolo di governance:
- La fase demo non e una scelta definitiva del provider dati live.
- La decisione finale avviene solo dopo evidenza tecnica + economica.

### 10.8 Mappatura esplicita su milestone e gate

| Workstream dati | Milestone primaria | Gate di uscita | Evidenza minima |
|---|---|---|---|
| Capture+Index+Dedup (demo) | **R2_PAPER_OPERATOR** | ingest stabile su set titoli ridotto | report run con `captured/skipped/duplicate` |
| Extract LLM + validator JSON | **R2_PAPER_OPERATOR** | parse deterministico con retry controllato | tasso validazione entro soglia KPI |
| Dataset builder test | **R2_PAPER_OPERATOR** | dataset riproducibile per backtest | checksum + rebuild identico |
| Decision pack fonte dati | **R4_GO_NO_GO** | scelta canale dati documentata | matrice costo/affidabilita/copertura |
| Provider switch controllato | **R5_LIVE_ENABLE** | attivazione fonte live human-confirmed | esito gate `paper/live` invariato |

### 10.9 KPI operativi aggiornati (data pipeline)

KPI obbligatori:
- `raw_on_change_only = 100%` (salvataggio raw solo su fingerprint nuovo).
- `duplicate_skip_rate >= 70%` su run ripetuti stesso universo.
- `valid_first_pass >= 85%` (LLM output JSON valido al primo tentativo).
- `valid_after_retry >= 97%` (dopo retry guidato).
- `needs_review_rate <= 3%`.
- `storage_cap_respected = true` (cap disco configurato, es. 2-5 GB per raw cache).
- `rebuild_determinism = true` (stesso input -> stesso dataset finale).

### 10.10 Guardrail anti-spreco e resilienza

Controlli minimi:
1. Fingerprint SHA256 su payload raw e chiave univoca `(source, symbol, page_type, fingerprint)`.
2. Finestra di freschezza per evitare capture ridondanti.
3. Retention + pruning automatico (TTL + cap dimensionale).
4. Log strutturato per audit (`captured`, `skipped_fresh`, `duplicate`, `extracted`, `rejected`, `needs_review`).

Assunzioni operative sul canale sito reale:
- rischio anti-bot/captcha considerato basso nel profilo d'uso attuale (accessi limitati e distribuiti);
- resta attivo fail-safe su segnali `403/429` con stop automatico della fonte e alert operativo.

### 10.11 Struttura backlog aggiornata (integrazione chirurgica)

Senza alterare gli epic esistenti A/B/C, aggiungere sotto-workstream:
- **EPIC-B (LLM Enablement controllato)**
  - B3 = capture selettivo + dedup + retention.
  - B4 = extractor Ollama (`qwen2.5`) con schema JSON rigido e retry.
  - B5 = validator + dataset builder + metriche pipeline.
- **EPIC-C (Misurazione e adozione)**
  - C3 = decision matrix provider dati (demo vs paid realtime vs delayed free vs sito reale).
  - C4 = trigger formale di switch verso R5 in base a KPI e cost model.

Con questa integrazione il piano resta coerente con metriche, milestone e struttura, e include in modo esplicito il percorso `demo-first` prima della scelta live.
