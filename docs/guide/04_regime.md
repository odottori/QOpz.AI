# Capitolo 3 — Il Regime
## Il contesto cambia tutto

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

### Cosa può andare storto

| Situazione | Segnale che vedi | Causa probabile | Cosa fare |
|------------|-----------------|-----------------|-----------|
| Regime bloccato su UNKNOWN | Badge grigio "UNKNOWN" nella WAR ROOM che non cambia | L'algoritmo HMM non ha ricevuto dati di mercato sufficienti per classificare il regime, oppure il feed dati è interrotto | Verifica che la connessione a IBKR sia attiva. Controlla lo stato della pipeline dati nella WAR ROOM. Se il badge rimane grigio dopo 30 minuti di mercato aperto, rilancia la sessione. |
| Regime non si aggiorna da ore | Il badge mostra sempre lo stesso regime per tutta la giornata, anche in presenza di movimenti bruschi | Il processo di aggiornamento periodico si è bloccato, oppure c'è un errore silenzioso nel ciclo di calcolo | Controlla i log di sistema. Riavvia il backend se necessario. Non operare con un regime fermo: senza aggiornamento, le protezioni di sizing non sono affidabili. |
| Regime passa a SHOCK inaspettatamente | Il badge diventa rosso SHOCK senza che tu abbia visto movimenti particolari | Un picco improvviso di volatilità implicita o un dato macro ha fatto scattare la soglia. Può essere un falso positivo su dati thin di fine seduta. | Non forzare operazioni. Aspetta il briefing del mattino successivo. Se il mercato è effettivamente tranquillo, il regime tornerà a NORMAL nel ciclo successivo. Non ignorare il segnale anche se sembra strano. |
| Badge regime assente nella UI | Il secondo pannello della WAR ROOM non mostra nessun badge regime | Il componente UI non ha ricevuto risposta dall'endpoint di stato, oppure il backend non è raggiungibile | Ricarica la pagina. Se il badge rimane assente, verifica che il backend sia in ascolto sulla porta 8765. Con il regime assente, non aprire nuove posizioni. |
