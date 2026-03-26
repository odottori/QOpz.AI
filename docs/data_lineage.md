# DATA LINEAGE LOGICO - DATI -> ANALISI -> OUTPUT

## 1) Obiettivo operativo
Definire in modo univoco:
- quali dati entrano nel modello,
- dove vengono trasformati,
- quali output producono,
- quali gate sbloccano i tab successivi.

## 2) Catena logica (end-to-end)
1. **Sorgenti esterne**
   - IBKR (conto, posizioni, chain, prezzi, greche)
   - YFinance (fallback prezzi/IV quando IBKR non fornisce dato utile)
   - Calendari/macro (earnings, ex-dividend, macro)
2. **Ingestione**
   - `POST /opz/data/refresh` esegue acquisizione e popolamento blocchi DATI.
   - Scheduler `morning/eod` esegue la stessa logica in unattended.
3. **Persistenza strutturata**
   - `feed_log` (stato run per feed)
   - `symbol_snapshots` (record per simbolo usato da Dati derivati)
4. **Validazione modello**
   - stato per riga/blocco (`ok` / `parz` / `err`)
   - conteggio simboli validi (non solo simboli totali)
5. **Analisi**
   - Step 3: regime
   - Step 4: scoring/shortlist/forecast candidati
6. **Output operativi**
   - tab ANALISI/BRIEFING, forecast, segnali, messaggi (es. QOpz Pulse), OP/POST.

## 3) Matrice tracciabilita (dove e come)
| Input | Dove entra | Trasformazione | Dove salvato | Dove usato | Output |
|---|---|---|---|---|---|
| IBKR chain/prezzi/greche | `api/routers/pipeline.py` | normalizzazione feed + qualita + fallback mirati | `feed_log`, `symbol_snapshots` | Tab DATI, derivati, analisi | righe feed + simboli validi |
| YFinance fallback | `api/routers/pipeline.py` | integrazione prezzo/IV quando IBKR non sufficiente | `symbol_snapshots` | DATI derivati, analisi pre-market | continuita dati simbolo |
| Macro + calendario eventi | pipeline feed dedicati | validazione completezza per giornata | `feed_log` | DATI, briefing, contesto rischio | eventi operativi |
| Universe/scan | scan + regime/scoring | shortlist e ranking candidati | tabelle universe/opportunity | ANALISI, BRIEFING, OP | forecast candidati |
| Stato scheduler | session runner + session logs | esecuzioni morning/eod | `session_logs` | UI card cron + log | controllo unattended |

## 4) Regole gate (allineamento richiesto)
### 4.1 Dati derivati (blocco)
- `ERR` se simboli totali = 0
- `PARZ` se simboli totali > 0 ma `OK = 0`
- `OK` se `OK >= 1`

### 4.2 Riga IBKR "Greche complete"
- deve usare **conteggio simboli validi del modello** (righe `OK` in Dati derivati)
- `ERR` se validi = 0
- `OK` se validi > 0
- se qualita e 83%, la metrica simboli deve mostrare i validi (es. `5`) oppure esplicitare denominatore (`5/6`), mai solo `6`.

### 4.3 Sblocco tab
- `DATI pronta` => sblocca `ANALISI`, `BRIEFING`, `OP`, `POST`
- `DATI non pronta` => resta accessibile solo `DATI` + monitoraggio.

## 5) Cosa fa ANALISI (in pratica)
### Step 3 - Regime
- classifica il mercato (NORMAL/CAUTION/SHOCK),
- determina sizing operativo base.

### Step 4 - Scoring
- costruisce shortlist candidati,
- calcola score/pilastri (vol, liquidity, risk-reward, regime-align),
- determina "pronti" da passare a briefing/operativita.

## 6) Strumenti minimi di supporto
- **Ingest automatica**: scheduler morning/eod + `data/refresh`.
- **Osservabilita**: `feed_log`, `session_logs`, `system log` con errori deduplicati.
- **Audit dati**: report lineage per blocco (input -> output -> consumer).
- **Gate espliciti UI**: regole di sblocco centralizzate e leggibili.

## 7) Riferimenti codice (entrypoint)
- `api/routers/pipeline.py`
- `api/routers/universe.py`
- `api/routers/sessions.py`
- `api/routers/regime.py`
- `ui/src/App.tsx`
