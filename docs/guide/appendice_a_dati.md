# Appendice A — Cosa guardiamo e perché
## (E cosa non guardiamo — e perché comunque lo sappiamo)

---

### Il principio di base: cause vs effetti

Esistono due modi di leggere i mercati.

Il primo modo è seguire le **cause**: notizie economiche, dichiarazioni delle banche centrali, risultati trimestrali delle aziende, tensioni geopolitiche, tweet dei CEO. Il mondo è pieno di investitori che cercano di capire cosa succederà e come il mercato reagirà.

Il secondo modo è guardare gli **effetti**: come si sta muovendo la volatilità? Il mercato sta già prezzando qualcosa di importante? Le opzioni sono care o economiche rispetto alla loro storia?

QOpz.AI sceglie il secondo approccio — e non per pigrizia, ma per una ragione precisa.

---

### Perché non usiamo le news?

La risposta breve è: **le news sono già dentro i dati che usiamo**.

Ecco come funziona. Quando si avvicina un evento importante — i risultati trimestrali di Apple, una riunione della Federal Reserve, un dato sull'inflazione — i market maker lo sanno. E sanno che l'incertezza aumenta. Allora alzano i prezzi delle opzioni per compensare il rischio aggiuntivo.

Questo aumento si riflette immediatamente nella **volatilità implicita** e nell'**IVR**.

In altre parole: il mercato delle opzioni ha già digerito la notizia *prima ancora che venga pubblicata*. L'IVR alto non ti dice cosa succederà — ti dice che il mercato si aspetta che succeda qualcosa di importante. E per la nostra strategia, è esattamente quello che ci serve sapere.

Aggiungere un feed di notizie non aggiungerebbe informazione — aggiungerebbe rumore.

---

### Il problema delle news come dato grezzo

Elaborare le notizie in modo utile richiede:

- Capire se la notizia è positiva o negativa *(sentiment)*
- Capire per quale azienda o settore è rilevante *(entity recognition)*
- Capire se è già nota al mercato o è una sorpresa *(novelty)*
- Capire quanto è importante rispetto ad altre notizie dello stesso giorno *(relevance scoring)*

Questo è un problema di intelligenza artificiale complesso, costoso, e con un margine di errore significativo. E alla fine, quello che ottieni è una stima di come il mercato *potrebbe* reagire — quando puoi semplicemente guardare come il mercato *sta già reagendo* attraverso IV e regime.

---

### Cosa usiamo e perché

| Dato | Perché lo usiamo |
|------|-----------------|
| **IVR** | Misura se le opzioni sono care o economiche. Alto = mercato nervoso, premi gonfiati. Basso = mercato tranquillo, premi compressi. |
| **Volatilità implicita** | Il mercato che prezza l'incertezza futura in tempo reale. Include già le aspettative su eventi noti. |
| **Delta** | Misura la distanza tra il prezzo corrente e il nostro strike. Più è basso, più siamo al sicuro. |
| **DTE** | Giorni alla scadenza. Governa la velocità del theta decay e il nostro margine temporale. |
| **Open interest e volume** | Misura la liquidità. Dove c'è liquidità, ci sono controparti — possiamo entrare e uscire senza sorprese. |
| **Spread bid-ask** | Il costo implicito di ogni operazione. Spread stretto = mercato efficiente. Spread largo = mercato illiquido. |
| **Regime HMM** | Cattura lo stato complessivo del mercato — incluso l'effetto di notizie già avvenute e la tensione accumulata prima di eventi attesi. |

---

### Cosa NON usiamo e perché

| Dato escluso | Perché non lo usiamo |
|-------------|---------------------|
| **News feed** | Il loro effetto è già prezzato nella IV. Aggiungerebbero rumore, non segnale. |
| **Sentiment sui social** | Altamente manipolabile, ritardato rispetto al mercato, difficile da calibrare. |
| **Dati macro grezzi** *(PIL, inflazione, occupazione)* | Il mercato li processa in millisecondi. Quando li leggiamo noi, sono già nel prezzo. |
| **Earning date** | Gestiti implicitamente: la IV esplode prima degli earnings, l'IVR sale sopra soglia, il regime può passare a CAUTION. Il sistema lo vede senza saperlo esplicitamente. |
| **Fondamentali aziendali** *(P/E, ricavi, debito)* | Irrilevanti per le opzioni a breve termine. Il prezzo dell'opzione dipende dal movimento del sottostante, non dal suo valore intrinseco. |
| **Order flow istituzionale** | Richiede dati livello 2 costosi e latenza ultra-bassa. Fuori scope per questo sistema. |

---

### Il vantaggio nascosto: la semplicità

Un sistema che usa meno dati ma li usa bene è superiore a un sistema che usa molti dati male.

Ogni dato aggiuntivo è una variabile in più da calibrare, una fonte in più che può smettere di funzionare, un modo in più per introdurre errori. La semplicità non è un compromesso — è una scelta di design.

Il mercato delle opzioni ha già fatto il lavoro di aggregare migliaia di informazioni in un unico numero: il prezzo. La volatilità implicita è la sintesi di tutto quello che il mercato collettivamente sa e si aspetta. Noi leggiamo quella sintesi — e la leggiamo bene.

---

### Una nota sull'imprevedibile

Esiste una categoria di eventi che nessun sistema può anticipare: il cigno nero. L'evento che nessuno si aspettava, che non è prezzato da nessuna opzione, che arriva senza preavviso.

Per questi casi, QOpz.AI non promette protezione anticipatoria — ma garantisce **contenimento del danno**: il rischio massimo di ogni posizione è sempre definito prima dell'apertura, il regime passa rapidamente a SHOCK bloccando nuovi trade, e il kill switch è sempre disponibile.

Non puoi prevedere tutto. Puoi però fare in modo che l'imprevedibile non ti distrugga.
