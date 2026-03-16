# Capitolo 4 — Le Protezioni
## Perché il sistema non si fida nemmeno di se stesso

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
