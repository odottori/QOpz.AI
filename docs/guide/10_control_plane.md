# Capitolo 10 — Il Control Plane operativo
## IBWR, Observer Telegram e Kill switch

---

### Cos'è il Control Plane

Il Control Plane è il pannello che governa l'infrastruttura del sistema, non i singoli trade. Contiene tre interruttori: il gateway ordini (IBWR), il canale di notifica Telegram (Observer) e il kill switch di emergenza. Capire come funzionano e come si condizionano a vicenda è essenziale per gestire situazioni fuori dall'ordinario in modo controllato.

---

### IBWR — Il gateway ordini

**Cos'è**

IBWR è il componente che traduce le decisioni del sistema in ordini reali su Interactive Brokers. Quando è attivo, il sistema può inviare ordini al broker. Quando è disattivato, il sistema continua a lavorare — analisi, scan, preview — ma non invia nulla.

**Dove si vede nella UI**

Nella barra superiore della War Room compare il badge **IBWR** con due stati:

| Badge | Cosa significa |
|-------|---------------|
| **ON** (verde) | Il gateway è attivo, gli ordini confermati vengono inviati a IBKR |
| **OFF** (rosso) | Il gateway è fermato, nessun ordine viene trasmesso |

**Quando fermarlo**

- Stai riavviando o aggiornando TWS o IBG
- Stai facendo modifiche al conto Interactive Brokers (deposito, cambio permessi)
- Hai rilevato un comportamento anomalo e vuoi fermare l'esecuzione in modo pulito, senza toccare il kill switch di emergenza
- Sei in una fase di solo osservazione e non vuoi che il sistema apra posizioni

**Effetto sul sistema**

Quando IBWR viene fermato dalla UI, il kill switch si attiva automaticamente come misura di sicurezza aggiuntiva. Questo significa che anche se IBWR venisse riattivato, nessun ordine passerebbe finché il kill switch non viene rimosso esplicitamente.

---

### Observer Telegram — Le notifiche operative

**Cos'è**

L'Observer è il sistema di notifiche via Telegram. Quando è attivo, il sistema invia messaggi al canale configurato per: aperture e chiusure di posizioni, cambi di regime, sessioni mattutine e EOD completate, avvisi critici (kill switch attivato, errori gravi) e il briefing audio giornaliero.

**Dove si vede nella UI**

Nella barra superiore compare il badge **Observer**:

| Badge | Cosa significa |
|-------|---------------|
| **ON** (verde) | Notifiche attive, IBKR connesso, kill switch inattivo |
| **OFF** (rosso) | Notifiche sospese, kill switch attivo |

Se al mattino il badge è OFF senza che l'operatore l'abbia spento, significa che qualcosa ha interrotto la connessione durante la notte. Prima di procedere, verifica lo stato di IBKR.

**Quando ha senso tenerlo spento**

- Durante la manutenzione di IBKR, quando non si vuole ricevere notifiche di stato intermedio
- In un ambiente di sviluppo in cui Telegram non è configurato (il badge Observer non compare affatto in questo caso)

**Regola importante:** l'Observer può essere riattivato solo se IBKR è connesso. Se IBKR non risponde, il tentativo di riattivazione viene bloccato automaticamente e il kill switch rimane attivo.

---

### Kill switch — L'arresto di emergenza

**Cos'è**

Il kill switch è un blocco che impedisce al sistema di eseguire qualsiasi ordine, indipendentemente dallo stato degli altri componenti. Quando è attivo, nessun ordine può essere confermato — anche se IBWR è acceso.

**Dove si trova nella UI**

Il kill switch ha un pannello dedicato nella War Room, sempre visibile indipendentemente dallo stato del sistema. Include il pulsante **Attiva kill switch** (per fermarlo) e **Rimuovi kill switch** (per riabilitare l'esecuzione).

**Quando usarlo**

- Situazione di mercato anomala in cui vuoi bloccare tutto immediatamente
- Hai rilevato un problema di esecuzione e non hai tempo di analizzare prima di fermare
- Stai passando la gestione a qualcun altro e vuoi uno stato sicuro come punto di partenza

**Effetti immediati**

All'attivazione: tutti gli ordini in preview non possono essere confermati, l'Observer passa a OFF, il badge IBWR mostra che l'esecuzione è bloccata. Il sistema continua a girare — analisi, scan, regime check — ma non esegue nulla.

---

### Come interagiscono i tre componenti

I tre interruttori non sono indipendenti: si condizionano in modo preciso.

- Se l'Observer passa a **OFF** (manualmente o per perdita di connessione IBKR), il kill switch si attiva automaticamente.
- Se IBWR viene fermato dalla UI, il kill switch si attiva automaticamente.
- Se il kill switch è attivo, l'Observer mostra OFF e nessun ordine può essere eseguito, anche se IBWR risulta acceso.

Il percorso per riportare il sistema in stato operativo completo è sempre lo stesso: prima risolvi il problema alla base, poi riattiva IBWR, poi rimuovi il kill switch, infine riattiva l'Observer.

---

### Procedura: manutenzione IBKR

Questo è il flusso da seguire ogni volta che devi riavviare, aggiornare o modificare TWS o IBG.

**Prima di iniziare**

1. Verifica nella War Room che non ci siano sessioni in corso (il badge Scheduler non deve essere in stato "In esecuzione").
2. Vai al pannello Control Plane e premi **Ferma IBWR**. Il sistema attiva automaticamente il kill switch e, se configurato, invia una notifica Telegram di conferma.
3. Verifica che il badge IBWR mostri OFF e che il kill switch sia attivo.

**Esegui la manutenzione**

Riavvia TWS o IBG, esegui gli aggiornamenti o le modifiche al conto necessarie.

**Dopo la manutenzione**

4. Aspetta che la connessione IBKR torni visibile nella War Room (badge IBKR verde).
5. Premi **Avvia IBWR** nel pannello Control Plane.
6. Premi **Rimuovi kill switch**.
7. Se l'Observer non torna ON automaticamente, premi **Attiva Observer**.
8. Controlla che tutti i badge nella barra superiore siano verdi prima di riprendere l'operatività.

---

### Cosa può andare storto

| Situazione | Segnale nella UI | Causa probabile | Cosa fare |
|------------|-----------------|-----------------|-----------|
| Observer mostra OFF senza che l'operatore l'abbia spento | Badge Observer rosso al mattino | IBKR si è disconnesso durante la notte, oppure un errore ha attivato il kill switch automaticamente | Verifica lo stato di IBKR. Se connesso, riattiva l'Observer dal pannello Control Plane |
| IBWR non risponde al comando on/off | Badge rimane invariato, nessuna conferma Telegram | Il servizio di control plane sulla VM non è raggiungibile | Controlla i log dell'API (`GET /opz/control/status`). Se il campo `control_plane_ok` è `false`, c'è un problema di connessione alla VM |
| Kill switch attivo ma l'operatore non ricorda di averlo attivato | Badge kill switch rosso, campo `activated_at` nel file di trigger | Il kill switch può essere attivato automaticamente da: Observer spento, IBWR fermato, o da una sessione che ha incontrato un errore critico | Leggi il motivo nel pannello kill switch (campo "attivato da"). Se la causa è risolta, procedi con la sequenza normale di ripristino |
| Badge Observer assente | Nessun badge Observer nella barra | Telegram non è configurato nell'ambiente corrente (sviluppo o paper senza credenziali Telegram) | In sviluppo è normale. In paper/live, verifica le credenziali Telegram nella configurazione |
| Stato incoerente: IBWR ON e kill switch ON contemporaneamente | Badge IBWR verde, badge kill switch rosso | IBWR è stato riattivato senza prima rimuovere il kill switch | Rimuovi il kill switch dal pannello. Il kill switch sovrascrive sempre IBWR: nessun ordine passa finché è attivo |

---

### Riferimento rapido

| Operazione | Endpoint | Body |
|-----------|----------|------|
| Ferma IBWR | `POST /opz/ibwr/service` | `{"action": "off"}` |
| Avvia IBWR | `POST /opz/ibwr/service` | `{"action": "on"}` |
| Stato IBWR | `POST /opz/ibwr/service` | `{"action": "status"}` |
| Ferma Observer | `POST /opz/execution/observer` | `{"action": "off"}` |
| Avvia Observer | `POST /opz/execution/observer` | `{"action": "on"}` |
| Attiva kill switch | `POST /opz/execution/kill_switch` | `{"action": "activate"}` |
| Disattiva kill switch | `POST /opz/execution/kill_switch` | `{"action": "deactivate"}` |
| Stato sistema | `GET /opz/control/status` | — |
