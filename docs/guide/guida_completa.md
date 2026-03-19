# QOpz.AI — Guida Completa
*Prefazione + Capitoli 0–7 + Appendice A*

---

## Prefazione — Prima di tutto, capisci cosa stai facendo

---

### Il mercato non è un nemico. È una conversazione.

Ogni giorno, su ogni borsa del mondo, milioni di persone comprano e vendono. Ognuna convinta di sapere qualcosa che l'altra non sa. Il prezzo che vedi in un grafico non è altro che il risultato di questo disaccordo continuo — un numero che cambia ogni secondo perché c'è sempre qualcuno che la pensa diversamente.

In questo rumore c'è una cosa interessante: **il mercato a volte esagera**. Si spaventa troppo. Oppure diventa troppo euforico. Quando esagera, crea opportunità — piccole, precise, misurabili.

QOpz.AI è nato per trovare quelle opportunità, valutarle con criteri chiari, e presentartele — senza fretta, senza emozione, senza rumore.

---

### Perché le opzioni? Un esempio semplice.

Immagina di essere un assicuratore.

Non guidi tu le macchine degli altri — ma ogni mese incassi un premio da chi vuole essere protetto dagli incidenti. Se non succede niente di grave, il premio è tuo. Se succede qualcosa, paghi — ma **il massimo che puoi perdere lo conosci già prima di firmare la polizza**.

Le opzioni su spread funzionano esattamente così. Non stai scommettendo che il mercato salga o scenda. Stai dicendo:

> *"Sono disposto a scommettere che il mercato non si muova oltre questo livello, entro questa data."*

E in cambio di questa scommessa, incassi un premio.

Il massimo che puoi perdere è scritto nero su bianco prima ancora di aprire il trade. Il premio che incassi è già in tasca dal momento in cui apri la posizione. Non ci sono sorprese nascoste.

---

### Il vero nemico non è il mercato. Sei tu.

Chiunque abbia mai investito lo sa: il problema non sono i numeri. È la testa.

La paura quando i prezzi scendono e vorresti vendere tutto. L'avidità quando salgono e vorresti raddoppiare. L'impulso di *fare qualcosa* quando sarebbe meglio non fare nulla. L'attaccamento a una posizione che sta andando male — *"tanto si riprende"* — fino a quando non si riprende più.

Un sistema non ha paura. Non si annoia. Non si eccita.

**QOpz.AI è il tuo copilota — non il tuo pilota automatico.** Il sistema fa il lavoro pesante: raccoglie i dati, filtra il rumore, calcola le opportunità, monitora le posizioni aperte. Tu mantieni sempre il controllo. Nessun ordine parte senza la tua conferma esplicita. Mai.

---

### Come è fatto questo documento

Nelle pagine che seguono troverai ogni componente del sistema spiegata con parole semplici e esempi concreti. Non serve essere matematici o programmatori — serve curiosità e voglia di capire davvero lo strumento che stai usando.

Ogni capitolo risponde a una domanda precisa:

- **Perché questo approccio?** E non un altro?
- **Da dove vengono i dati?** E come si sa se sono affidabili?
- **Come il sistema riconosce un'opportunità?** E perché ne scarta il 90%?
- **Cos'è il "regime di mercato"?** E perché cambia tutto?
- **Come vengono protetti i tuoi soldi** quando qualcosa va storto?
- **Come si legge la WAR ROOM?** Pannello per pannello, numero per numero.

Alla fine di questo percorso saprai spiegare QOpz.AI a chiunque. E soprattutto — lo controllerai davvero, non solo lo userai.

---

*Buona lettura.*

---
---

## Capitolo 0 — Il Perché
### Prima di ogni numero, prima di ogni grafico: perché?

---

### Perché fare trading in modo sistematico?

Prova a ricordare l'ultima volta che hai preso una decisione importante sotto pressione. Forse funzionava bene, forse no. Ma quasi certamente non era la tua decisione migliore — perché il cervello umano sotto stress non ragiona, *reagisce*.

Il mercato è progettato per metterti sotto pressione. I prezzi si muovono mentre guardi. Le notizie si accumulano. Gli altri sembrano sempre sapere qualcosa che tu non sai. In questo ambiente, le decisioni emotive — comprare quando tutti comprano, vendere quando tutti vendono — sono la norma. E la norma, statisticamente, perde.

Il trading sistematico nasce da una premessa semplice:

> *Se scrivi le tue regole quando sei calmo, e le segui quando il mercato è agitato, hai già un vantaggio sulla maggior parte degli altri.*

Non perché le regole siano magiche. Ma perché la disciplina è rara — e la rarità, nei mercati, si paga.

---

### Perché le opzioni?

Compri un'azione e speri che salga. Se scende, perdi. La direzione conta tutto — e indovinare la direzione del mercato, nel breve periodo, è sostanzialmente un lancio di moneta con commissioni.

Le opzioni aggiungono una dimensione che le azioni non hanno: **il tempo**.

Ogni opzione ha una scadenza. E il tempo, per chi vende opzioni, è un alleato silenzioso. Ogni giorno che passa senza che il mercato si muova troppo, il valore dell'opzione che hai venduto diminuisce — a tuo favore. I matematici lo chiamano *theta decay*. Puoi immaginarlo come una clessidra: ogni granello di sabbia che cade è un piccolo guadagno per chi ha venduto l'opzione.

Non devi indovinare dove va il mercato. Devi solo scommettere che **non vada troppo lontano** — in un senso o nell'altro.

---

### Perché i credit spread e non le opzioni nude?

Vendere opzioni senza protezione è come fare l'assicuratore senza un contratto di riassicurazione. Funziona finché non arriva l'uragano — e quando arriva, le perdite possono essere illimitate.

Il credit spread risolve questo problema in modo elegante: vendi un'opzione *e contemporaneamente ne compri un'altra* a un prezzo d'esercizio più lontano. La seconda costa meno di quello che hai incassato — quindi incassi comunque un premio netto. Ma soprattutto, **definisce il tuo rischio massimo prima ancora di aprire la posizione**.

È come costruire una rete di sicurezza sotto il trapezio. Non elimina il rischio — ma lo rende misurabile, gestibile, prevedibile.

---

### Perché questo approccio e non un altro?

Esistono decine di strategie di trading. Scalping, momentum, mean reversion, carry trade — ognuna con i suoi pregi e i suoi rischi. Allora perché questo?

**Tre ragioni concrete:**

**1. Si adatta a chi ha un'altra vita.**
Non richiede di stare incollato agli schermi tutto il giorno. Le opzioni si muovono lentamente rispetto alle azioni. Un'opportunità aperta oggi sarà ancora lì domani. Il sistema monitora per te — e ti avvisa solo quando c'è qualcosa che merita la tua attenzione.

**2. Il rischio è sempre definito.**
Prima di aprire qualsiasi posizione, sai già il massimo che puoi perdere. Non è una stima. Non è una speranza. È un numero scritto nel contratto. Questo cambia completamente il modo in cui dormi la notte.

**3. La probabilità lavora strutturalmente per te.**
Un credit spread ben costruito ha una probabilità di successo che parte dal 60–70% per design — non per fortuna. Non significa che vinci sempre. Significa che, su un numero sufficiente di operazioni, la matematica tende dalla tua parte.

---

### Perché adesso?

Non perché il momento sia perfetto — il momento perfetto non esiste. Ma perché la tecnologia che rende tutto questo possibile per un singolo operatore privato è disponibile oggi, a costo zero o quasi. Dati, algoritmi, connessioni ai broker, interfacce professionali — fino a qualche anno fa erano il privilegio esclusivo delle grandi istituzioni finanziarie.

QOpz.AI non è un sistema per diventare ricchi in fretta. È uno strumento per operare con metodo, con protezioni, con trasparenza — e con la consapevolezza di cosa sta succedendo e perché.

Questo documento esiste proprio per questo: perché uno strumento che non capisci non lo controlli. E uno strumento che non controlli, prima o poi, ti sorprende.

---

### Una scelta fondamentale: cause o effetti?

C'è un ultimo "perché" da chiarire — e riguarda il tipo di informazioni su cui il sistema si basa.

Il mondo è pieno di dati: notizie economiche, dichiarazioni delle banche centrali, risultati aziendali, tensioni geopolitiche. Migliaia di investitori ogni giorno cercano di interpretare queste *cause* per anticipare come reagirà il mercato.

QOpz.AI fa una scelta diversa: **guarda gli effetti, non le cause.**

Quando si avvicina un evento importante — una riunione della Fed, i risultati di un'azienda, un dato sull'inflazione — i partecipanti al mercato lo sanno già. E alzano automaticamente i prezzi delle opzioni per compensare l'incertezza attesa. Questo aumento è immediatamente visibile nella volatilità implicita.

In altre parole: **il mercato delle opzioni ha già digerito la notizia prima ancora che venga pubblicata.** L'IVR alto non ti dice cosa succederà — ti dice che qualcosa di importante è atteso, e che il mercato ti sta pagando bene per assumerti il rischio.

Aggiungere un feed di notizie non aggiungerebbe informazione utile — aggiungerebbe rumore da filtrare. La volatilità implicita è già la sintesi di tutto quello che il mercato collettivamente sa e si aspetta.

Questa scelta — guardare gli effetti invece delle cause — è il principio che guida la selezione di ogni singolo dato che il sistema utilizza.

---

*Nel prossimo capitolo vedremo esattamente quali sono questi dati, da dove arrivano, e come il sistema decide se fidarsi di loro.*

---
---

## Capitolo 1 — I Dati
### Da dove arriva quello che il sistema sa?

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
---

## Capitolo 2 — I Filtri
### Perché il sistema scarta il 90% delle opportunità

---

### Il filtro è una forma di rispetto

Un buon analista non considera tutto. Sceglie dove guardare. Sa che il tempo e il capitale sono limitati, e che sprecarli su opportunità mediocri significa non avere risorse quando arriva quella buona.

QOpz.AI applica questa logica in modo sistematico attraverso una serie di **filtri duri** — regole non negoziabili che eliminano automaticamente tutto ciò che non rispetta i criteri minimi. Non c'è eccezione. Non c'è "ma forse stavolta". O passa o non passa.

---

### I filtri duri: le regole non negoziabili

**1. Lo spread bid-ask non può superare il 10% del prezzo mid**

Ogni opzione ha un prezzo di acquisto e uno di vendita. La differenza tra i due è il costo che paghi al mercato solo per entrare nella posizione — ancora prima di guadagnare o perdere qualcosa.

Se questa differenza è troppo alta, il mercato ti sta dicendo che quell'opzione è illiquida — pochi la comprano, pochi la vendono. Entrare e uscire da posizioni illiquide è costoso e rischioso.

> Spread superiore al 10%: eliminato.

**2. Il costo dello spread per giorno non può essere eccessivo**

C'è una variante più sofisticata del filtro precedente. Un'opzione con spread al 8% e 45 giorni alla scadenza è molto diversa da una con spread al 8% e 15 giorni alla scadenza. Nel secondo caso, quel costo si concentra in molti meno giorni — è come pagare lo stesso affitto per una stanza più piccola.

Il sistema calcola lo *spread cost per DTE* — il costo giornaliero dello spread — e rifiuta le opzioni dove questo costo è troppo alto rispetto al tempo rimasto.

> Costo giornaliero eccessivo: eliminato.

**3. L'open interest deve essere almeno 100 contratti**

L'open interest è il numero di contratti aperti in questo momento su quella specifica opzione. Un numero basso significa pochi partecipanti, spread ampi, difficoltà a uscire dalla posizione quando vuoi.

Vuoi stare dove c'è movimento, dove il mercato è vivo.

> Open interest sotto 100: eliminato.

**4. La scadenza deve essere tra 14 e 60 giorni**

Troppo vicino alla scadenza *(sotto 14 giorni)*: il tempo che rimane è poco, i movimenti di prezzo impattano molto di più, il margine di errore si azzera. È come cercare di frenare una macchina a 100 km/h su una strada che finisce tra 10 metri.

Troppo lontano dalla scadenza *(oltre 60 giorni)*: il premio incassato è lontano nel tempo, il capitale rimane bloccato a lungo, le incertezze aumentano.

La finestra 14–60 giorni è il punto dolce: abbastanza tempo per lavorare, abbastanza vicino per incassare presto.

> DTE fuori range: eliminato.

**5. L'IVR deve essere almeno 20**

Come spiegato nel capitolo precedente, un IVR basso significa che i premi delle opzioni sono compressi. Vendere opzioni economiche non è conveniente — stai assumendo rischio per un compenso insufficiente.

> IVR sotto 20: eliminato.

**6. Il margine richiesto non può superare il 30% del capitale**

Ogni posizione richiede una garanzia — il broker la chiama margine. Se una singola operazione richiede troppa garanzia, stai concentrando troppo rischio in un posto solo e rischi di non avere capitale per altre opportunità — o per gestire l'imprevisto.

> Margine superiore al 30%: eliminato.

---

### Dopo i filtri: lo scoring a 4 pilastri

Quello che sopravvive ai filtri duri non è ancora automaticamente buono — è solo *ammissibile*. Entra quindi in una fase di valutazione più sfumata: lo scoring.

Il sistema assegna un punteggio a ogni opportunità basandosi su quattro dimensioni:

**Pilastro 1 — Qualità della volatilità**
Quanto è alto l'IVR? Quanto premio stai incassando rispetto alla media storica? Un IVR alto significa che il mercato ti sta pagando bene per assumerti il rischio.

**Pilastro 2 — Qualità dello spread**
Il bid-ask è stretto? Il prezzo mid è stabile? L'open interest è robusto? Questi elementi misurano quanto è facile entrare e uscire dalla posizione.

**Pilastro 3 — Posizione del delta**
Il delta dell'opzione dice quanto sei "esposto" al movimento del mercato. Un delta troppo alto significa che sei vicino al prezzo corrente — un piccolo movimento ti mette in difficoltà. Un delta troppo basso significa che incassi troppo poco. Il sistema cerca il punto di equilibrio.

**Pilastro 4 — Allineamento con il regime**
Questo è il pilastro che collega tutto al contesto più ampio. Un'opportunità ottima in un mercato tranquillo può essere un'opportunità pessima in un mercato sotto stress. Il regime — di cui parleremo nel prossimo capitolo — è il filtro finale che dà senso a tutto il resto.

---

### Il risultato: poche opportunità, ben selezionate

Il 90% di quello che esiste sul mercato non passa i filtri. Non perché il mercato sia povero di opportunità — ma perché il sistema è selettivo per design. Meglio fare poche operazioni buone che molte operazioni mediocri.

Quello che arriva sulla tua scrivania è già stato setacciato, pesato, valutato. Il tuo compito è decidere se confermare o ignorare — con tutte le informazioni necessarie già davanti a te.

---

*Nel prossimo capitolo, il concetto più importante di tutto il sistema: il regime di mercato.*

---
---

## Capitolo 3 — Il Regime
### Il contesto cambia tutto

---

### La stessa mossa, risultati opposti

Un chirurgo esperto sa che la stessa operazione può avere esiti molto diversi a seconda delle condizioni del paziente. In un paziente giovane e sano, è routine. Nello stesso paziente con una febbre alta e pressione instabile, è un rischio molto più alto.

Il mercato funziona allo stesso modo. La stessa strategia di opzioni — con gli stessi parametri, lo stesso sottostante, lo stesso premio — può essere un'ottima operazione in un mercato tranquillo e un'operazione pericolosa in un mercato sotto stress.

Il **regime di mercato** è la risposta del sistema a questa realtà: prima di valutare qualsiasi opportunità, il sistema si chiede *in che tipo di mercato siamo oggi?*

---

### I tre regimi

**NORMAL — Mercato tranquillo**

La volatilità è nella norma. I prezzi si muovono, ma in modo ordinato. Non ci sono segnali di stress sistemico. In questa condizione, il sistema opera a piena capacità: tutte le strategie sono attive, il dimensionamento delle posizioni è al 100%.

**CAUTION — Mercato in allerta**

Qualcosa si sta muovendo. La volatilità è aumentata. I segnali mostrano che il mercato è più nervoso del solito — ma non ancora in crisi aperta. In questa condizione, il sistema diventa più selettivo: solo spread con margine di sicurezza maggiore, solo posizioni nella direzione giusta, dimensionamento ridotto al 50%.

È come guidare quando piove: non ti fermi, ma rallenti e aumenti la distanza di sicurezza.

**SHOCK — Mercato in crisi**

Il mercato si sta muovendo in modo disordinato. La volatilità è esplosiva. In queste condizioni, le opzioni si comportano in modo imprevedibile e i premi che sembravano attraenti possono diventare trappole. Il sistema si ferma completamente: nessun nuovo trade, dimensionamento zero.

Non è paura. È disciplina. I mercati in shock si riprendono — e quando si riprendono, le opportunità tornano. Meglio aspettare.

---

### Come il sistema riconosce il regime?

Dietro questa classificazione c'è un algoritmo chiamato **HMM** — Hidden Markov Model. Il nome suona complicato, ma l'idea di base è semplice.

Immagina di dover capire se fuori c'è bel tempo o brutto tempo, senza poter guardare dalla finestra. Hai solo una serie di misurazioni: temperatura, pressione atmosferica, umidità. Dall'insieme di questi segnali, riesci a inferire lo stato del tempo con buona approssimazione.

L'HMM fa la stessa cosa con i mercati. Non guarda un singolo indicatore — guarda l'insieme: volatilità realizzata, volatilità implicita, struttura dei prezzi, microstructura del mercato. E da questo insieme, classifica il regime corrente.

La classificazione viene aggiornata regolarmente — non aspetta che la situazione sia già esplosa per cambiare il giudizio.

---

### Perché il regime è il pilastro più importante

Torna alla metafora dell'assicuratore. Un buon assicuratore non calcola solo la probabilità di un incidente in condizioni normali. Sa che quando c'è un uragano in arrivo, la probabilità di sinistri sale verticalmente — e smette di vendere polizze nuove finché la tempesta non è passata.

Il regime è esattamente questo: il sistema che dice "oggi il mercato si comporta come in una giornata serena o come alla vigilia di una tempesta?"

Operare senza questa consapevolezza significa trattare tutti i giorni allo stesso modo — e il mercato, prima o poi, presenta il conto.

---

*Nel prossimo capitolo vediamo le protezioni: cosa succede quando qualcosa va storto — perché prima o poi, succede.*

---
---

## Capitolo 4 — Le Protezioni
### Perché il sistema non si fida nemmeno di se stesso

---

### Il principio fondante: ogni sistema può sbagliare

Un buon ingegnere non progetta un ponte pensando che non crollerà mai. Progetta un ponte che regge anche quando qualcosa va storto — un bullone allentato, un carico superiore al previsto, una tempesta imprevista.

QOpz.AI è stato progettato con la stessa filosofia. Non è stato costruito pensando "funzionerà sempre" — è stato costruito pensando "cosa succede quando qualcosa non funziona come previsto?"

Le protezioni non sono funzionalità accessorie. Sono la parte più importante del sistema.

---

### Protezione 1 — Tu sei sempre l'ultimo a decidere

Questa è la regola più importante di tutte, e vale la pena ripeterla chiaramente:

**Nessun ordine viene inviato al broker senza la tua conferma esplicita. Mai.**

Il sistema può trovare un'opportunità, valutarla, calcolare le dimensioni, preparare l'ordine — ma poi si ferma e aspetta. Ti mostra tutto quello che ha elaborato. Tu guardi, decidi, e solo se clicchi "conferma" l'ordine parte.

Questo non è un limite tecnico. È una scelta architetturale deliberata. Il trading algoritmico completamente automatico esiste — ma porta con sé rischi che non vale la pena correre per un operatore privato. Un bug nel codice, un dato errato, un momento di mercato anomalo — con l'automazione totale, il danno è già fatto prima che tu te ne accorga.

Con QOpz.AI, il danno non può partire senza il tuo via libera.

---

### Protezione 2 — Il Kill Switch

In qualsiasi momento, con un'azione semplice, puoi bloccare completamente il sistema. Non solo mettere in pausa — bloccarlo.

Quando il kill switch è attivo, il sistema si rifiuta di processare qualsiasi conferma d'ordine. Non importa cosa stia succedendo, non importa quale opportunità sia in corso — la risposta è no.

È l'interruttore di emergenza sulla parete della fabbrica. Non lo usi tutti i giorni — ma sai che c'è, e sai che funziona.

---

### Protezione 3 — Il Kelly Criterion e il suo cancello

Il Kelly Criterion è una formula matematica che calcola la dimensione ottimale di ogni posizione in funzione del vantaggio statistico che hai e della varianza dei risultati passati.

In teoria, è uno strumento potente. In pratica, può essere pericoloso se applicato su basi statistiche insufficienti — come cercare di calcolare la velocità media di un'auto dopo aver percorso solo 100 metri.

QOpz.AI lo disabilita completamente fino a quando non vengono soddisfatte due condizioni simultanee:

1. I dati provengono da fonti reali *(VENDOR_REAL_CHAIN)*
2. Il sistema ha registrato almeno 50 trade chiusi

Fino a quel momento, il dimensionamento è conservativo e fisso. Nessuna eccezione.

---

### Protezione 4 — Il trail degli eventi

Ogni cosa che succede nel sistema viene registrata. Ogni opportunità valutata. Ogni filtro applicato. Ogni ordine proposto, confermato, inviato, eseguito o rifiutato.

Non è burocrazia — è memoria. Se qualcosa va storto, puoi tornare indietro e capire esattamente cosa è successo, quando, e perché. Se il sistema prende una decisione che ti sembra strana, puoi vedere il ragionamento completo.

Questa trasparenza è una forma di controllo. Un sistema che non lascia tracce è un sistema di cui non ti puoi fidare.

---

### Protezione 5 — Niente ordini a mercato

Ogni ordine che QOpz.AI propone è sempre un ordine limite — con un prezzo preciso, non "al meglio del mercato".

Un ordine a mercato dice "compra o vendi al prezzo che trovi". In condizioni normali funziona. In condizioni di mercato agitato, può farti eseguire a un prezzo molto diverso da quello che ti aspettavi.

Un ordine limite dice "compra o vendi solo a questo prezzo, o meglio". Se il mercato non offre quel prezzo, l'ordine non viene eseguito. È meno conveniente in termini di velocità — ma è una protezione contro le esecuzioni sorprendenti.

---

### Protezione 6 — Il WFA e l'anti-leakage

Il sistema viene calibrato su dati storici — ma con una regola ferrea: i parametri vengono calcolati solo sui dati del passato, mai sui dati del futuro.

Questo potrebbe sembrare ovvio — ma nel mondo dell'analisi quantitativa è una trappola frequente. Si chiama *data leakage*: usare inconsapevolmente informazioni future per calibrare un modello del passato. Il risultato è un sistema che sembra funzionare alla perfezione sui dati storici — e poi fallisce completamente nella realtà.

QOpz.AI usa una tecnica chiamata **Walk-Forward Analysis**: divide il tempo in finestre, calibra su una finestra, testa sulla finestra successiva. Mai il contrario.

---

*Nell'ultimo capitolo vediamo dove tutto questo si materializza: la WAR ROOM — il pannello di controllo operativo.*

---
---

## Capitolo 5 — La WAR ROOM
### Come leggere il pannello di controllo

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
---

## Appendice A — Cosa guardiamo e perché
### (E cosa non guardiamo — e perché comunque lo sappiamo)

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

---
---

## Capitolo 6 — Il Viaggio di un Trade
### Dalla catena di opzioni al profitto incassato

*Questo capitolo è disponibile come presentazione interattiva.*

👉 [Apri Il Viaggio di un Trade →](trade_lifecycle.md)

Il capitolo illustra passo per passo, con numeri reali, come nasce un trade: dalla selezione nella catena di opzioni, attraverso i filtri e lo score, fino all'esecuzione, alla gestione attiva e alla chiusura. Ogni tappa mostra esattamente cosa vede l'operatore in quel momento nella WAR ROOM.

---
---

# Capitolo 7 — Tier e strategie
## Come cresce il sistema con il tuo capitale

---

### Non tutte le strategie sono adatte a ogni situazione

Un pilota impara prima su un Cessna, poi su un Boeing. Non perché il Boeing sia troppo difficile in astratto — ma perché per controllarlo bene servono ore di volo, riflessi calibrati, e una comprensione profonda di ciò che può andare storto. Nessun istruttore responsabile ti mette alla cloche di un jet alla prima lezione.

QOpz.AI funziona allo stesso modo. Il sistema ha quattro livelli operativi — chiamati **tier** — che si sbloccano man mano che il tuo capitale cresce e la tua esperienza matura. Non è una limitazione artificiale: le strategie più complesse richiedono più margine, più attenzione, e una maggiore tolleranza agli errori temporanei. Portarle troppo presto è l'errore più comune — e più costoso.

---

### I quattro livelli

**MICRO (€1.000–€2.000)** è il punto di partenza. Il sistema opera esclusivamente con il Bull Put spread su IWM — una posizione alla volta, due al massimo. È la strategia più semplice della famiglia: vendi una put, compri una più lontana per limitare il rischio, incassi il premio. L'obiettivo non è la massima redditività — è imparare il ciclo completo senza la complessità di più gambe o più posizioni simultanee.

**SMALL (€2.000–€5.000)** aggiunge due strategie: l'Iron Condor e il Wheel. Fino a tre posizioni simultanee. È il livello in cui la gestione diventa vera gestione: posizioni diverse, scadenze diverse, stati diversi. Serve avere un metodo, non solo intuizione.

**MEDIUM (€5.000–€15.000)** estende l'universo a SPY e QQQ, aggiunge strategie direzionali avanzate come PMCC e Calendar spread, e introduce TWAP/VWAP per l'esecuzione. Fino a cinque posizioni simultanee.

**ADVANCED (€15.000+)** aggiunge il Ratio Spread e le strategie multi-sottostante. Fino a otto posizioni. A questo livello, il sistema si comporta come un piccolo book di opzioni — con tutti i rischi e i benefici che ne conseguono.

---

### L'Iron Condor — Guadagnare dall'immobilità

Immagina di essere convinto che IWM nei prossimi 30 giorni non si muoverà molto. Non sai in quale direzione andrà — ma sei ragionevolmente sicuro che non farà un movimento estremo né verso l'alto né verso il basso.

L'Iron Condor è costruito esattamente per questa situazione. Combina due spread speculari: un put spread che guadagna se il mercato non scende troppo, e un call spread che guadagna se il mercato non sale troppo. Insieme formano una "finestra" di redditività — incassi il premio se il prezzo rimane tra le due opzioni vendute fino alla scadenza.

Il tuo alleato è il tempo: ogni giorno che passa senza un movimento estremo erode il valore delle opzioni che hai venduto. Il tuo nemico è il movimento forte e direzionale — se il mercato sfonda uno dei due lati, la perdita è definita e conosciuta prima di aprire la posizione. Nessuna sorpresa.

---

### Il Wheel — Guadagnare in attesa

La strategia Wheel funziona in cicli. Non è pensata per chi vuole esposizione direzionale — è pensata per chi vuole reddito sistematico su un sottostante che sarebbe comunque disposto a detenere.

Il ciclo inizia con una **Cash-Secured Put**: vendi una put su IWM, incassi un premio, e ti impegni ad acquistare 100 azioni se la put viene esercitata. Hai abbastanza liquidità in conto per farlo. Se la put scade senza essere esercitata, tieni il premio e ricomincia. Se viene esercitata, ricevi le 100 azioni al prezzo di strike.

A quel punto sei nella fase di **assegnazione**: hai le azioni. Il tuo costo effettivo è lo strike meno il premio già incassato — non hai perso nulla, hai semplicemente cambiato forma al tuo capitale. E adesso vendi una **Covered Call**: un'opzione call sulle azioni che hai, con strike uguale o superiore al tuo costo di acquisto. Incassi un altro premio. Se la call scade, vendi un'altra. Se viene esercitata, le azioni vengono "chiamate via" al prezzo di strike — incassi la differenza di prezzo più tutti i premi accumulati durante il ciclo.

Il ciclo ricomincia.

La Wheel non è una strategia ad alto rendimento immediato. È una macchina che trasforma il tempo e la pazienza in reddito — a condizione di essere disposti a detenere le azioni in caso di assegnazione e di avere la disciplina di non scegliere strike troppo ottimistici.

---

### Come il sistema sceglie la strategia per te

Il sistema conosce il tuo tier, il tuo active mode (che puoi tenere inferiore al tier se preferisci), e il regime corrente. Da questi tre dati costruisce la lista delle strategie eligibili per quel momento specifico.

In regime **NORMAL**, tutte le strategie del tuo tier sono disponibili. Il sistema le ordina per punteggio e ti presenta le opportunità più interessanti.

In regime **CAUTION**, il sistema diventa selettivo in modo automatico. Iron Condor e Wheel vengono sospesi — l'IC perché un mercato nervoso può sfondare facilmente i livelli venduti, il Wheel perché CAUTION non è il momento di accumulare posizioni lunghe su azioni. Rimane solo il Bull Put, con sizing al 50%.

In regime **SHOCK**, nessuna nuova proposta. La gestione dell'esistente resta attiva, ma il sistema non suggerisce nuovi trade finché il regime non torna nella norma.

---

### I gate di avanzamento

Passare da MICRO a SMALL non è automatico. Il sistema richiede di dimostrare che ha funzionato — non in teoria, ma su trade reali. I criteri principali: almeno 50 operazioni chiuse, Sharpe out-of-sample ≥ 0.6, drawdown massimo ≤ 15% in qualsiasi finestra temporale, nessuna violazione delle regole operative, e DATA_MODE impostato su dati reali (non sintetici).

Non puoi accelerare questi gate. Servono trade veri su dati veri — è l'unico modo per sapere che il sistema funziona nel tuo contesto specifico, non solo nei backtest. Chi brucia le tappe di solito scopre perché esistono.

---

### Una cosa concreta: lo stato delle posizioni Wheel

Ogni posizione Wheel aperta è tracciata nel sistema con il suo stato preciso: in attesa (IDLE), put venduta (OPEN_CSP), azioni assegnate (ASSIGNED), call venduta (OPEN_CC), ciclo completato (CLOSED). Il pannello operativo mostra sempre in quale fase si trova ogni posizione.

Questo è più importante di quanto sembri. La Wheel può durare settimane. Le azioni possono rimanere nel portafoglio attraverso diversi cicli di covered call. Avere uno stato chiaro e persistente — non nella tua testa, ma nel sistema — è la differenza tra una gestione disciplinata e una caotica.

---

*Il ciclo completo di un trade — dalla catena di opzioni al profitto incassato — è documentato in dettaglio nel capitolo [Il Viaggio di un Trade](trade_lifecycle.md).*
