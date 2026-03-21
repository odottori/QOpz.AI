# Capitolo 1 — I Dati
## Da dove arriva quello che il sistema sa?

---

### Il problema di partenza: non tutti i dati sono uguali

Immagina di dover decidere se uscire con l'ombrello basandoti sulle previsioni meteo. Se le previsioni vengono da una stazione meteorologica professionale con sensori calibrati, ti fidi. Se vengono da qualcuno che ha guardato il cielo dalla finestra, forse meno.

Nel trading, la qualità dei dati non è un dettaglio tecnico — è la fondamenta di tutto. Una decisione presa su dati sbagliati è peggio di una decisione casuale, perché ti dà una falsa sicurezza.

QOpz.AI gestisce questo problema in modo esplicito: ogni singolo dato che entra nel sistema porta con sé un'etichetta che dice da dove viene e quanto ci si può fidare.

---

### Cosa entra nel sistema?

Per ogni opzione che il sistema valuta, vengono raccolte queste informazioni:

**Dati di mercato base:**
- Il prezzo a cui qualcuno è disposto a comprare *(bid)* e a cui qualcuno è disposto a vendere *(ask)*
- Il prezzo di mezzo *(mid)* — il valore "equo" stimato
- Quanti contratti sono aperti in questo momento *(open interest)*
- Quanti contratti sono stati scambiati oggi *(volume)*

**Dati specifici delle opzioni:**
- Il *delta* — quanto si muove il prezzo dell'opzione per ogni euro di movimento del sottostante
- La *volatilità implicita* — quanto il mercato si aspetta che le cose si muovano nei prossimi giorni
- Il *DTE* — giorni alla scadenza *(Days To Expiration)*

**Il dato più importante: IVR**

L'IVR *(IV Rank)* merita una spiegazione separata perché è uno dei filtri più potenti del sistema.

Immagina che nel corso dell'ultimo anno la volatilità di un'azione sia oscillata tra 15 e 45. Oggi è a 40. Questo significa che la volatilità è alta rispetto alla sua storia recente — il mercato è nervoso, i premi delle opzioni sono gonfiati. Vendere opzioni in questo momento significa incassare più del solito.

L'IVR misura esattamente questo: **dove si trova la volatilità oggi rispetto al suo intervallo storico**, su una scala da 0 a 100. Un IVR di 70 significa che la volatilità è più alta del 70% dei giorni dell'ultimo anno. Un IVR di 10 significa che è quasi ai minimi storici — non è un buon momento per vendere opzioni.

Il sistema non considera nemmeno un'opportunità se l'IVR è sotto 20.

---

### La fiducia nei dati: il DATA_MODE

Ogni record che entra nel database porta un'etichetta chiamata **DATA_MODE**. Esistono solo due valori possibili:

**`SYNTHETIC_SURFACE_CALIBRATED`**
Dati simulati, costruiti matematicamente per sembrare reali. Utili per testare e sviluppare il sistema senza spendere soldi in abbonamenti a dati reali. Il sistema funziona, i calcoli sono corretti — ma stai allenando su un simulatore, non sulla pista vera.

> Watermark obbligatorio su ogni report. Kelly sizing disabilitato.

**`VENDOR_REAL_CHAIN`**
Dati reali, forniti da un provider professionale, con la catena completa di opzioni aggiornata. È la modalità che conta davvero.

> Kelly sizing abilitato solo dopo 50 trade chiusi con dati reali.

Questa distinzione non è un dettaglio tecnico — è una protezione. Il sistema si rifiuta di usare il dimensionamento aggressivo finché non ha visto abbastanza dati veri per giustificarlo.

---

### Cosa succede se i dati sono vecchi?

Un prezzo di un'opzione aggiornato tre ore fa non vale nulla per prendere una decisione adesso. Il sistema traccia per ogni dato il momento in cui è stato prodotto *(asof_ts)* e il momento in cui è arrivato nel database *(received_ts)*. Se il dato è troppo vecchio, viene ignorato.

È come la data di scadenza sul cibo: non importa quanto sembri fresco — se è scaduto, non lo mangi.

---

*Nel prossimo capitolo vediamo cosa succede a questi dati una volta che arrivano: come il sistema decide cosa tenere e cosa buttare.*

---

## Cosa può andare storto

| Situazione | Segnale che vedi | Causa probabile | Cosa fare |
|------------|-----------------|-----------------|-----------|
| Watermark DATA_MODE = SYNTHETIC in UI | Badge arancione "SYNTHETIC" visibile su report e scan | IBKR non connesso o dati reali non disponibili — il sistema è caduto su dati simulati | Verifica connessione IBKR (porta 7496 paper / 7497 live); non aprire trade reali in questa condizione; Kelly rimane bloccato finché il watermark è attivo |
| IBKR offline, dati non aggiornati | asof_ts nell'interfaccia mostra orario di oltre 5 minuti fa; scan riusa dati vecchi | TWS/IBG disconnesso, timeout di rete, o riavvio del gateway durante la sessione | Controlla lo stato IBKR in TWS; riavvia il gateway se necessario; chiama `POST /opz/ibwr/service {"action": "off"}` poi `"on"` per forzare la riconnessione |
| Chain options vuota per un simbolo | Scan non mostra candidati per quel simbolo; nessun errore esplicito | Il simbolo non ha opzioni liquide nel range DTE 14–60, oppure il dato non è ancora arrivato dal provider | Attendi il prossimo ciclo di ingest; se persiste, verifica che il simbolo sia nel universo configurato; non aggiungere manualmente candidati senza dati validi |
| Qualità dati A+ vs B — differenza operativa | Indicatore di qualità sul record (source_quality nel log) | A+ = catena completa con Greeks verificati; B = dati parziali o Greeks stimati | Con qualità B evita strategie multi-gamba (Iron Condor, Calendar); preferisci Bull Put semplice; la differenza non blocca ma riduce l'affidabilità dello scoring |
