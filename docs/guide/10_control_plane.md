# Capitolo 10 — Il Control Plane operativo
## IBWR, Observer Telegram e gestione delle interruzioni

---

### Il control plane in sintesi

Il control plane è l'insieme dei comandi che permettono di gestire il sistema durante un'operazione o una manutenzione. Non riguarda i trade — riguarda l'infrastruttura: il servizio di esecuzione ordini (IBWR), il canale di notifica Telegram (Observer), e il kill switch di emergenza.

Capire questi tre strumenti e come interagiscono è fondamentale per gestire situazioni fuori dall'ordinario in modo controllato.

---

### IBWR — Il servizio di esecuzione ordini

**Cos'è**

IBWR è il componente che traduce le decisioni del sistema in ordini reali su Interactive Brokers. Quando è attivo, il sistema può effettivamente inviare ordini. Quando è disabilitato, il sistema continua a fare analisi, scan e preview — ma non invia nulla.

**Quando disabilitarlo**

- Stai aggiornando TWS o IBG e il broker ti chiede di riavviare
- Stai facendo manutenzione sul conto (deposito, bonifico, modifica permessi)
- Hai rilevato un comportamento anomalo e vuoi fermare l'esecuzione in modo pulito, senza attivare il kill switch di emergenza
- Sei in una fase di osservazione e non vuoi che il sistema apra posizioni automaticamente

**Come controllarlo**

```
POST /opz/ibwr/service
{
  "action": "off",         // oppure "on" o "status"
  "notify_telegram": true  // invia conferma su Telegram
}
```

Azioni disponibili:

| Azione | Effetto |
|--------|---------|
| `"on"` | Riattiva il servizio IBWR |
| `"off"` | Disattiva il servizio e attiva automaticamente il kill switch |
| `"status"` | Legge lo stato corrente senza modificarlo |

> Quando IBWR viene disattivato via API, il kill switch viene attivato automaticamente come misura di sicurezza aggiuntiva. Quando riattivi IBWR, dovrai anche disattivare il kill switch separatamente.

**Stato corrente**

Lo stato di IBWR è visibile nel pannello di stato del control plane:

```
GET /opz/control/status
```

Il campo `ibwr` nella risposta contiene lo stato corrente del servizio.

---

### Observer Telegram — Il canale di notifica

**Cos'è**

L'Observer è il sistema di notifiche via Telegram. Quando è attivo (ON), il sistema invia messaggi al canale configurato per:
- Conferme di apertura e chiusura posizioni
- Cambi di regime
- Sessioni morning/EOD completate
- Avvisi operativi (kill switch attivato, errori critici)
- Briefing audio generato

Quando è disattivato (OFF), nessuna notifica viene inviata — il kill switch viene attivato automaticamente come misura di sicurezza.

**Come controllarlo**

```
POST /opz/execution/observer
{
  "action": "on",           // oppure "off"
  "notify_telegram": true,  // invia conferma su Telegram della modifica
  "source": "operator_ui"
}
```

Regola importante: **l'Observer può essere attivato solo se IBKR è connesso**. Se IBKR non risponde, il tentativo di attivazione viene bloccato e il kill switch rimane attivo.

Questa regola evita situazioni in cui il sistema crede di stare notificando l'operatore mentre in realtà sta operando alla cieca.

**Badge Observer nella WAR ROOM**

Il badge Observer in alto nell'interfaccia mostra lo stato corrente:

| Badge | Significato |
|-------|-------------|
| **ON** (verde) | Notifiche attive, IBKR connesso, kill switch inattivo |
| **OFF** (rosso) | Notifiche sospese, kill switch attivo |

Se vedi il badge OFF al mattino quando non lo aspetti, significa che qualcosa ha interrotto la connessione durante la notte — controlla IBKR prima di procedere.

---

### Kill switch — L'arresto di emergenza

Il kill switch è descritto nel dettaglio nella WAR ROOM (Capitolo 5). In questo contesto è importante sapere come interagisce con IBWR e Observer:

- **Observer OFF** → kill switch attivato automaticamente
- **IBWR OFF** → kill switch attivato automaticamente
- **Kill switch attivo** → Observer mostra OFF, IBWR non può eseguire ordini

Per riportare il sistema in stato operativo completo, l'ordine corretto è:

1. Risolvi il problema alla base (riconnetti IBKR, completa la manutenzione, ecc.)
2. Riattiva IBWR: `POST /opz/ibwr/service {"action": "on"}`
3. Disattiva il kill switch: `POST /opz/execution/kill_switch {"action": "deactivate"}`
4. Riattiva l'Observer: `POST /opz/execution/observer {"action": "on"}`

---

### Workflow: "Voglio fare manutenzione su IBKR"

Questo è il flusso da seguire quando devi fermare TWS o IBG, aggiornarlo, o fare modifiche al conto.

**Prima di iniziare**

1. Verifica che non ci siano sessioni in corso (`GET /opz/session/status` — campo `"running": false`)
2. Disattiva IBWR:
   ```
   POST /opz/ibwr/service {"action": "off", "notify_telegram": true}
   ```
   Il sistema attiva automaticamente il kill switch e invia una notifica Telegram.

3. Verifica lo stato:
   ```
   GET /opz/control/status
   ```
   Conferma che `kill_switch_active: true` e `ibwr.state: "OFF"`.

**Esegui la manutenzione**

Riavvia TWS/IBG, aggiorna, fai le modifiche necessarie.

**Dopo la manutenzione**

4. Verifica che IBKR sia tornato online (connessione visibile nella WAR ROOM)
5. Riattiva IBWR:
   ```
   POST /opz/ibwr/service {"action": "on"}
   ```
6. Rimuovi il kill switch:
   ```
   POST /opz/execution/kill_switch {"action": "deactivate"}
   ```
7. Verifica che l'Observer sia tornato ON automaticamente o riattivalo:
   ```
   POST /opz/execution/observer {"action": "on", "notify_telegram": true}
   ```
8. Controlla `GET /opz/control/status` — tutti i semafori devono essere verdi.

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
