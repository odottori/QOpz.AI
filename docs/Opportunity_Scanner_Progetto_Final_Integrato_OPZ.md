# Opportunity Scanner — Versione Finale Integrata e Completa (OPZ)

**Architettura:** Broker-Centric, Human-in-the-Loop, Anti-Fragile

---

## Premessa

Questo progetto nasce dalla fusione di un approccio architetturale rigoroso con soluzioni pragmatiche no-code e best practice operative. Non richiede dati a pagamento né competenze di programmazione avanzate per l'avvio, ma è progettato per scalare verso l'automazione progressiva mantenendo sempre il controllo umano sui punti critici.

---

## Principi Fondamentali

1. **Il broker è l'unica fonte della verità per dati opzionali.**  
   Delta, gamma, theta, vega e volatilità implicita provengono direttamente dalle piattaforme professionali tramite API o data feed. Il sistema non ricostruisce ciò che il broker fornisce già calcolato. Questo elimina errori di pricing su opzioni americane, dividendi e early exercise.

2. **L'umano valida prima che la macchina filtri.**  
   Nessuna automazione totale in fase iniziale. L'algoritmo propone, l'operatore approva con consapevolezza. Solo i segnali esplicitamente convalidati entrano nel motore opzioni. Questo riduce i falsi positivi e costruisce un database di apprendimento essenziale per le fasi successive.

3. **Parametri battle-tested come default invariabili.**  
   Si parte da soglie consolidate nella pratica professionale:
   - Delta tra **0,15 e 0,50** per posizioni direzionali  
   - Giorni alla scadenza tra **20 e 45**  
   - Volume minimo **10** contratti  
   - Open interest minimo **500**  
   - Spread bid-ask massimo **10%** del prezzo medio  
   - Rapporto rischio-rendimento minimo **1,5** per spread  
   
   Non si ottimizza a caso. Si raccolgono dati reali, poi si aggiusta in base all'evidenza.

4. **Ogni trade alimenta il miglioramento continuo del sistema.**  
   Si traccia l'Expected Value teorico al momento dell'entry e si confronta sistematicamente con il profit and loss realizzato. Questo loop evidenzia bias del modello e guida l'evoluzione.

5. **Gestione esplicita delle trappole operative.**  
   Data gap notturno, liquidità apparente versus reale, eventi binari che invalidano i modelli: tutto viene anticipato e mitigato con procedure specifiche.

---

# FASE 1: Validazione Manuale (Settimane 1–4)

## Obiettivo

Confermare che la logica segnale–strategia–filtro genera edge misurabile prima di qualsiasi investimento in strumenti tecnologici. Costruire la base di dati qualitativi su cui fondare l'automazione successiva.

## Strumenti

- TradingView per lo screening tecnico  
- Thinkorswim (o equivalente) per l'analisi delle opzioni  
- Foglio di calcolo strutturato per il tracking  
- Calendario economico affidabile

## Flusso Operativo Giornaliero

### Screening pre-market (TradingView)
Eseguire uno screener con criteri predefiniti e salvati:
- Prezzo sopra la **media mobile 200 giorni** (trend)
- **RSI** in zone estreme (<30 o >70)
- **Bande di Bollinger** compresse (larghezza sotto il 10° percentile dei 6 mesi precedenti)
- **Volume** > media mobile a 20 giorni (conferma interesse)

Output: lista di **5–10** titoli candidati.

### Scelta strategia opzionale (manuale)
- Segnale rialzista + IV bassa → **debit spread** (es. bull call spread)
- Segnale rialzista + IV elevata → **credit spread** (es. bull put spread)
- Bollinger compresse + breakout atteso ma direzione incerta → **straddle/strangle long**
- Trend laterale forte con supporti/resistenze → **iron condor**

### Controllo calendario eventi (bloccante)
- Earnings entro **2 giorni** → **esclusione totale** (nessuna eccezione)
- Earnings tra **3–7 giorni** → solo strategie **vega-neutre/negative**, evitare long gamma
- Ex-dividend entro **5 giorni** → verifica rischio early assignment su call ITM

### Filtri su Option Chain (Thinkorswim Option Hacker)
- Delta **0,20–0,40** per posizioni long direzionali
- DTE **30–45**
- Spread bid-ask **<10%** del prezzo medio
- Volume **>10**
- Open interest **>500**

### Tracking (foglio di calcolo)
Campi minimi da registrare:
- Data/ora di ingresso, ticker
- Tipo di segnale tecnico
- Strategia opzionale
- Strike/scadenza
- Premio pagato/ricevuto
- Greche all’entry (incluse IV e rapporto IV/HV)
- Motivazione qualitativa
- Prezzo/data uscita
- P&L realizzato
- Giorni di detenzione
- Deviazione rispetto all’EV teorico all’ingresso

## Target per passare alla Fase 2
- ≥ **30 trades** documentati
- Win rate **>55%**
- Profit factor **>1,3**
- Chiarezza dei pattern che l’operatore tende ad approvare/scartare + motivazioni qualitative

---

# FASE 2: Semi-Automazione Broker-Centric con Human-in-the-Loop (Settimane 5–12)

## Componente A: Signal Engine con Validazione Umana

Un motore (es. Python su dati gratuiti) analizza l’universo titoli pre-market e genera una lista di candidati con **punteggio composito** (proposte, non segnali definitivi).

### Dashboard: sezione “Da Validare”
Per ogni candidato:
- Grafico prezzi + indicatori
- Punteggio composito + breakdown fattori
- Regime di mercato classificato
- Eventi imminenti (earnings/macro)
- Storico segnali simili + outcome trade

### Azioni operatore
- **Convalida**: approva e invia al filtro opzioni + confidenza (1–5)
- **Rifiuta**: scarta + motivazione testuale (training dataset)
- **Modifica**: aggiusta parametri e registra la differenza tra proposta algoritmo e giudizio umano

Solo i segnali convalidati (**max 5–10/giorno**) passano allo step successivo. Dopo ~100 validazioni, si verifica l’allineamento: l’algoritmo avrebbe preso le stesse decisioni dell’operatore?

---

## Componente B: Option Chain Analyzer con Gestione delle Trappole

### Meccanismo di caching anti data-gap
- Snapshot completo opzioni **15 min prima della chiusura**
- Include: bid/ask, volumi, OI, greche, IV, scadenze rilevanti
- Fonte primaria per analisi serali e setup mattina seguente (API paper/gratuite possono essere sporche/ritardate)
- Cache con scadenza max **18 ore**; oltre → marcata **obsoleta** con avviso esplicito

### Gerarchia filtri di liquidità
1. **Spread bid-ask %** (primario, inaggirabile)  
   - Max **10%**, ideale < **5%**
   - Scarto immediato se spread eccessivo anche con OI alto
2. **Volume sessione** (secondario): min **10**
3. **Open interest** (solo verifica struttura): min **500**
4. Spread tollerato per distanza da ATM:
   - ATM: fino a **10%**
   - 1 deviazione standard: fino a **15%**
   - Oltre: scarto automatico

### Filtro calendario eventi (bloccante)
- Earnings entro **2 giorni**: blocco totale (nessuna eccezione)
- Earnings **3–7 giorni**: flag evento imminente; preferenza vega-neutre/negative; sconsiglia long gamma
- Ex-dividend entro **5 giorni**: verifica early assignment call ITM + filtro strike rispetto a spot–dividendo
- Macro (FOMC, payroll, ecc.): flag incertezza + riduzione sizing

### Integrazione Expected Move
Per ogni scadenza:
- Expected Move implicito da straddle ATM:  
  (Prezzo call ATM + prezzo put ATM) / prezzo sottostante

Confronto sistematico tra target del segnale tecnico e Expected Move:
- Segnale 5% vs EM 2% → asimmetria informativa o rischio sottostimato (alta convinzione, alta varianza)
- Segnale 3% vs EM 8% → mercato prezza più rischio (vendita vol con cautela)
- Trade che puntano a movimento > **2× EM** → validazione umana obbligatoria

### Z-Score volatilità implicita (IV)
Calcolo su finestre **30 e 60 giorni**: (IV corrente − media storica) / deviazione standard storica
- Z < **−1,5** → IV cheap: opportunità **long vega** (se supportata dal segnale)
- Z > **+1,5** → IV expensive: opportunità **short vega** (attenzione eventi binari)
- −0,5 ≤ Z ≤ +0,5 → IV fair: decisione basata su altri fattori

Tracciamento Z all’entry per analisi post-trade: long a Z basso rende meglio? short a Z alto è sostenibile?

---

## Flusso dei dati (Fase 2)
1. Segnali convalidati → motore opzioni
2. Interrogazione API broker → catena completa con greche e IV già calcolate (**no pricing interno**)
3. Applicazione filtri: liquidità, eventi, delta, DTE
4. Calcolo punteggio “fit” strategia:
   - IV vs storica
   - distanza strike vs Expected Move
   - efficienza theta (income)
   - gamma (event-driven)
   - Z-Score IV
5. Output: top **5 opportunità** per segnale con metriche e qualificatori di qualità

---

## Componente C: Dashboard e Alert

### Dashboard — 3 pannelli
1. **Validazione segnali**: candidati + grafici + punteggi + regime + eventi + storico + azioni (convalida/rifiuta/modifica)
2. **Opportunità opzioni filtrate** (tabella): strike, scadenza, delta, IV, prezzo, punteggio fit, IV vs storica, Expected Move, Z-Score, distanza target, qualità dati, flag eventi
3. **Qualità e stato**: freschezza dati, Cache Mode, avviso cache >12h, spread % evidenziato, calendario eventi visivo, IV sulla distribuzione storica

### Alert Telegram
Riassunto opportunità:
- qualità dati + età cache
- alert eventi (countdown)
- Expected Move vs target segnale
- Z-Score IV con interpretazione
- spread/liquidità
- greche essenziali
- prezzo + dettagli contratto
- avvertenze (check manuali / riduzioni size)

---

## Componente D: Database e Tracking

### Tabella segnali
- dati algoritmici completi
- esito validazione umana
- confidenza
- motivazione rifiuto (se applicabile)
- regime di mercato
- eventi noti alla generazione

### Tabella opportunità
- dati broker grezzi originali
- spread calcolato
- Expected Move
- Z-Score IV
- distanza segnale vs Expected Move
- qualità dati (real-time o cache)
- flag eventi attivi
- punteggio fit strategia

### Tabella trades
- prezzi entry/exit
- P&L realizzato
- EV teorico all’entry + probabilità di profitto
- profitto max teorico, perdita max teorica, breakeven
- Z-Score IV all’entry, Expected Move all’entry
- errore previsione (realizzato vs atteso)
- slippage stimato
- holding period
- regime di mercato durante trade
- eventi intervenuti durante detenzione

### Tabella analisi
- aggregazioni settimanali: per strategia, range Z-Score, distanza segnale vs EM, regime
- bias sistematici
- raccomandazioni di aggiustamento + livello confidenza

---

## Componente E: Analisi Settimanale EV vs P&L

Report automatico settimanale: confronto EV teorico vs risultati reali, segmentato per:
- strategia
- range Z-Score
- livello confidenza umana
- regime di mercato

Esempi output:
- credit spread sovrastima win rate del 15% → riduzione sizing 25% fino a revisione
- confidenza 5 performa come atteso; confidenza 1–2 peggiore del previsto del 30%
- regime alta volatilità: rischio sottostimato
- long opzioni con Z < −1: realized return +40% vs media

Da queste analisi emergono raccomandazioni operative che modificano i default o attivano circuit breaker.

---

# FASE 3: Automazione Selettiva con Circuit Breaker Avanzati (Settimane 13–20)

## Criterio di ingresso
- ≥ **100 segnali** validati con tracking completo
- evidenza che algoritmo avrebbe selezionato gli stessi segnali approvati dall’uomo nell’**80%** dei casi
- bias EV contenuto entro **15%** per le strategie principali

## Transizione graduale
- Settimane iniziali: auto-convalida solo punteggio > **0,90** (pattern confermato), review EOD
- Progressivamente: soglia intervento umano a **0,85** e poi **0,80**
- Finale: full auto con circuit breaker

## Circuit breaker
- **Bias EV:** se bias >20% su una strategia → stop strategia + revisione manuale
- **Liquidità:** se >30% opportunità in sessione con spread >15% → stop + avviso condizioni anomale
- **Eventi:** se indice volatilità sale >20% in una sessione → modalità validazione umana obbligatoria per 24h
- **Dati:** se cache usata per >50% tickers in sessione → stop + refresh manuale

---

## Parametri di default (configurabili con evidenza)

- **Liquidità**
  - spread bid-ask max **10%** (ideale <5%)
  - volume min **10**
  - open interest min **500**
  - tolleranza spread in funzione distanza da ATM

- **Temporali**
  - DTE **20–45**
  - caching automatico **15 min** prima chiusura
  - scadenza cache **18 ore**

- **Greci**
  - delta **0,15–0,50** (long direzionali)
  - delta max **0,30** (credit spread)
  - delta max **0,20** (iron condor)

- **Eventi**
  - blocco earnings entro **2 giorni**
  - flag/restrizioni earnings **3–7 giorni**
  - verifica early assignment dividendi entro **5 giorni**
  - riduzione sizing su macro

- **Volatilità**
  - Z-Score IV < **−1,5** → long vega
  - Z-Score IV > **+1,5** → short vega
  - validazione obbligatoria se target segnale / Expected Move > **2**

- **Rischio**
  - esposizione max singola posizione **2%** capitale
  - esposizione settoriale max **20%**
  - limite posizioni correlate **3**
  - riduzione sizing **25%** su flag eventi o regime incertezza

---

## Checklist Operativa Giornaliera

- **Mattina pre-market**
  - verifica freschezza dati (real-time vs cache)
  - review calendario eventi
  - screener + validazione segnali + confidenza

- **Apertura mercato**
  - conferma visiva spread effettivi
  - verifica Expected Move vs cache (overnight)
  - cross-check liquidità su top 3 contratti

- **Durante la sessione**
  - monitor alert eventi/condizioni anomale
  - logging immediato modifiche manuali

- **Sera**
  - salvataggio cache automatico + conferma
  - review trades chiusi + deviazioni
  - verifica report settimanale (se giorno analisi)
  - backup database

---

## Strumenti e costi

- **Fase 1:** zero costi; strumenti gratuiti; **paper trading obbligatorio**
- **Fase 2:** dati zero costi con API paper; hosting opzionale **5–10€/mese**; librerie Python open source
- **Fase 3:** zero costi per API paper o conto minimo; upgrade dati professionali solo dopo edge consistente

---

## Metriche di successo per fase

- **Fase 1**
  - 30 trades completi
  - pattern approvati/rifiutati chiari
  - win rate >50% e profit factor >1,2

- **Fase 2**
  - tempo operativo −50% con KPI invariati
  - validazioni umane 20%–40% dei segnali (selettività)
  - database ≥100 segnali validati con tracking EV

- **Fase 3**
  - Sharpe >1
  - Max drawdown <15%
  - circuit breaker <1/mese in condizioni normali
  - convergenza win rate atteso vs realizzato entro ±10%

