# Backtest Classico vs Replay Operativo

## Scopo

Questo progetto contiene due modalita` distinte di validazione storica. Non vanno confuse.

## 1. Backtest classico

Il backtest classico usa dataset storici strutturati e metriche quantitative standard.

Caratteristiche:
- input principale: dataset CSV o Parquet riproducibile
- focus: rendimenti, Sharpe, Max Drawdown, Win Rate, WFA/OOS
- scopo: validare modelli offline e certificare robustezza quantitativa

Artefatti principali nel repo:
- `scripts/run_backtest.py`
- `scripts/wfa_bull_put.py`
- `tests/test_f2_t4_wfa_bull_put.py`
- `tests/test_f2_t5_run_backtest.py`

Nel planner attuale, `F2-T5` appartiene a questo filone.

## 2. Replay operativo

Il replay operativo non e` un semplice backtest prezzi.
Simula il comportamento reale del sistema spostando l'"oggi" indietro nel tempo e avanzando passo dopo passo con sola informazione disponibile in quel momento.

Caratteristiche:
- input principale: snapshot, journal, eventi, stato, decisioni operatore, metriche paper
- focus: causalita`, decision flow, gating, conferme umane, stato ordini, compliance
- scopo: simulare il comportamento end-to-end del sistema come avrebbe operato in una finestra storica

Artefatti gia` presenti nel repo:
- `execution/paper_metrics.py`
- `execution/journal_state.py`
- `execution/state_machine.py`
- `api/opz_api.py`
- `tests/test_f6_t1_paper_metrics.py`
- `tests/test_f6_t2_api_journal.py`
- `tests/test_f6_t2_go_nogo_pack.py`

Questo filone oggi esiste come infrastruttura paper/operator-grade, ma non e` ancora esposto come runner unico dedicato.

## Stato attuale

- Il backtest classico e` esplicito e implementato.
- Il replay operativo e` implicito ma reale: esiste nei moduli execution/paper/operator.
- La demo pipeline F1-T5..F1-T8 alimenta soprattutto il backtest classico, ma alcune sue parti sono utili anche al replay operativo per snapshot, provenance e retention.

## Regola di lettura corretta

Quando il progetto parla di:
- `dataset`, `CSV`, `WFA`, `OOS`, `Sharpe`, `backtest`: si riferisce al backtest classico
- `paper`, `journal`, `operator`, `state machine`, `go/no-go`, `equity snapshots`: si riferisce al replay operativo o alla sua infrastruttura

## Implicazione pratica

Non bisogna dichiarare chiuso il "backtest" del progetto con il solo `F2-T5`.
`F2-T5` chiude il backtest classico sul dataset disponibile.
Il replay operativo richiede un runner separato o una formalizzazione esplicita del percorso paper/replay gia` presente.
