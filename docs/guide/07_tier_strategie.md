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

*Nel prossimo capitolo vediamo come leggere la WAR ROOM — il pannello operativo che raccoglie in un unico posto tutto quello che serve per decidere.*
