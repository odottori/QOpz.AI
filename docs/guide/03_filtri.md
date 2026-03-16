# Capitolo 2 — I Filtri
## Perché il sistema scarta il 90% delle opportunità

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
