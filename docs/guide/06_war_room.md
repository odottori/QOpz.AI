# Capitolo 5 — La WAR ROOM
## Come leggere il pannello di controllo

---

### Non una dashboard. Una stanza operativa.

Il nome non è casuale. Una war room è il posto dove le persone che devono prendere decisioni importanti si riuniscono con tutte le informazioni disponibili davanti a loro — niente di superfluo, tutto quello che serve.

La WAR ROOM di QOpz.AI è organizzata in tre pannelli. Ognuno risponde a una domanda diversa.

---

### Pannello 1 — Come sta andando?

Il primo pannello mostra la salute complessiva del sistema e del portafoglio.

**La curva dell'equity** racconta la storia del capitale nel tempo. Non un numero statico — una linea che mostra come il valore del portafoglio è evoluto, giorno dopo giorno. Una linea che sale gradualmente con piccoli ritracciamenti è esattamente quello che ci si aspetta da una strategia di vendita di opzioni ben gestita.

**Il drawdown** mostra quanto sei distante dal tuo massimo storico. Un drawdown del 5% significa che sei il 5% sotto il tuo picco. Ogni sistema ha i suoi drawdown — l'importante è che rimangano entro i limiti attesi e si recuperino nel tempo.

**I gate** sono semafori. Verde significa che tutto è in ordine. Giallo significa che qualcosa richiede attenzione. Rosso significa che qualcosa non funziona come dovrebbe — e il sistema ti dice cosa.

---

### Pannello 2 — Cosa sta facendo il sistema in questo momento?

Il secondo pannello mostra lo stato operativo in tempo reale.

**Il regime corrente** è il primo dato che devi guardare. NORMAL, CAUTION o SHOCK — questo colore ti dice in che tipo di mercato stai operando oggi e cosa puoi fare.

**Lo stato della connessione** mostra se il sistema è collegato al broker, se i dati stanno arrivando, se tutte le componenti stanno funzionando. Come il cruscotto di un'auto: non ci pensi quando tutto va bene, ma quando si accende una spia, la noti subito.

**La pipeline dei dati** mostra il percorso che i dati fanno dal momento in cui arrivano al momento in cui diventano opportunità valutate. Ogni passo ha il suo stato: completato, in corso, in attesa. Se un passo si blocca, sai esattamente dove.

---

### Pannello 3 — Cosa devo fare adesso?

Il terzo pannello è quello più operativo — quello che guardi quando devi prendere una decisione.

**Il conto IBKR** mostra il capitale disponibile, il margine utilizzato, il margine libero. Questi numeri cambiano in tempo reale in base alle posizioni aperte e ai movimenti di mercato.

**Gli exit candidates** sono le posizioni già aperte che il sistema ha identificato come meritevoli di attenzione. Non tutte le posizioni aperte — solo quelle per cui sta succedendo qualcosa di rilevante.

Il sistema assegna a ognuna un punteggio di urgenza basato su tre criteri:

*Theta decay* — la posizione ha già raggiunto il 70% del profitto massimo possibile. In questo caso, tenere aperta la posizione espone a rischio senza un compenso adeguato. Meglio chiuderla e liberare capitale.

*Loss limit* — la posizione ha perso più del 50% del premio inizialmente incassato. Il segnale che la direzione del mercato si è mossa contro di te in modo significativo. Non aspettare che peggiori.

*Time stop* — mancano 7 giorni o meno alla scadenza. Con poco tempo rimasto, le opzioni si comportano in modo più imprevedibile. Meglio uscire in modo controllato che aspettare gli ultimi giorni.

**Quando compare il badge 🚨 EXIT** nell'intestazione del terzo pannello, significa che almeno una posizione ha un punteggio di urgenza alto. Non è un allarme di panico — è un segnale che richiede la tua attenzione nelle prossime ore.

---

### Come usare la WAR ROOM nella pratica

Non devi guardare la WAR ROOM continuamente. Non è pensata per questo.

L'uso tipico è:

**Al mattino, prima dell'apertura del mercato** — guardi il regime, verifichi che tutto sia connesso, controlli se ci sono exit candidates urgenti.

**A metà giornata** — una rapida occhiata agli exit candidates, al margine disponibile, ai gate.

**Alla sera, dopo la chiusura** — verifichi l'equity della giornata, guardi se ci sono opportunità nuove da considerare per il giorno successivo.

Per tutto il resto del tempo, il sistema lavora per te. Se qualcosa richiede attenzione urgente, ricevi un alert — e solo allora apri la WAR ROOM.

---

### Una nota finale sul controllo

La WAR ROOM è progettata per darti informazioni, non per farti sentire in balia degli eventi. Ogni numero ha un contesto. Ogni segnale ha una spiegazione. Ogni azione richiede la tua conferma.

Uno strumento che capisci è uno strumento che controlli. E uno strumento che controlli, anche nei momenti difficili, rimane uno strumento — non diventa un problema.

---

### Il NARRATORE — Briefing audio integrato

Il NARRATORE è la barra di ascolto nella WAR ROOM. Ti permette di ascoltare un riassunto vocale della situazione operativa senza dover leggere ogni pannello singolarmente.

**Come aprire il drawer**

Il NARRATORE è disponibile come pannello espandibile nella WAR ROOM. Clicca sulla barra **NARRATORE** per aprirlo. Il drawer mostra:

- Il player audio con i controlli di riproduzione (indietro / play-pause / avanti)
- La lista dei briefing disponibili (ultimi 20)
- Il pulsante per generare un nuovo briefing

**Play e pause**

Usa i controlli **◀ PREV / ▶ PLAY / NEXT ▶** per navigare tra i briefing disponibili e controllare la riproduzione. Il player funziona inline — non apre finestre esterne.

**Generare un nuovo briefing**

Il briefing viene generato raccogliendo i dati correnti dal sistema (regime, equity, opportunità, exit candidates) e convertendoli in audio tramite il motore di sintesi vocale `edge-tts`. Per generare:

```
POST /opz/briefing/generate
```

Parametri opzionali:
- `no_telegram=true` — non invia il briefing su Telegram dopo la generazione (default: invia)

Prerequisito: `edge-tts` deve essere installato nell'ambiente Python. Se non è installato, la generazione scade in timeout (120 secondi) con un messaggio esplicativo.

**Cosa contiene il briefing**

Il briefing vocale riassume:
- Regime corrente e tendenza
- Equity e drawdown del conto
- Uscite urgenti (se presenti)
- Principali opportunità del giorno

**Lista briefing disponibili**

```
GET /opz/briefing/list
```

Restituisce i filename degli ultimi 20 briefing MP3 disponibili, ordinati per data discendente.

**Ascoltare un briefing specifico**

```
GET /opz/briefing/latest        — il più recente
GET /opz/briefing/file/{nome}   — un file specifico per nome
```

---

### Il badge Observer — Stato delle notifiche Telegram

In alto nell'interfaccia della WAR ROOM compare il badge **Observer**. Indica se il canale di notifica Telegram è attivo.

| Badge | Significato operativo |
|-------|-----------------------|
| **ON** (verde) | Notifiche attive, IBKR connesso, esecuzione sbloccata |
| **OFF** (rosso) | Notifiche sospese, kill switch attivo, nessun ordine possibile |

Se vedi il badge OFF al mattino senza averlo disattivato tu, significa che qualcosa ha interrotto la connessione a IBKR durante la notte. Prima di fare qualsiasi operazione, verifica che TWS/IBG sia attivo e controlla `GET /opz/control/status`.

Per i dettagli su come gestire l'Observer, vedi il Capitolo 10 — Il Control Plane operativo.
