# Capitolo 9 — Il Session Scheduler
## Sessioni automatiche mattutine e serali

---

### Cos'è

Il Session Scheduler avvia automaticamente due cicli operativi ogni giorno di mercato: uno la mattina, prima dell'apertura delle borse americane, e uno a fine giornata, dopo la chiusura. Senza scheduler, queste operazioni andrebbero avviate manualmente ogni giorno.

---

### Cosa vede l'operatore

Nella barra superiore della War Room compare un badge **Scheduler** con tre possibili stati:

| Badge | Cosa significa |
|-------|---------------|
| **Attivo** (verde) | Lo scheduler è abilitato e aspetta l'orario programmato |
| **In esecuzione** (arancione, lampeggiante) | Una sessione è in corso in questo momento |
| **Inattivo** (grigio) | Lo scheduler è disabilitato in configurazione — le sessioni si avviano solo manualmente |

Accanto al badge compare l'orario della prossima sessione prevista, es. "Prossima: mattina alle 09:00 ET".

---

### Flusso normale

**Ogni mattina (ore 09:00 ET, giorni di mercato)**

Lo scheduler si attiva automaticamente. Il sistema controlla il regime di mercato (NORMAL / CAUTION / SHOCK), scansiona l'universo di simboli in cerca di opportunità e prepara il briefing del giorno. Al termine, il risultato viene registrato nello storico delle sessioni.

L'operatore trova il briefing aggiornato nella War Room quando apre il pannello al mattino — non deve fare nulla.

**Ogni fine giornata (ore 16:30 ET, giorni di mercato)**

Lo scheduler avvia la sessione EOD. Il sistema registra lo snapshot di equity del conto, controlla le posizioni aperte e chiude le metriche della giornata. Anche questo avviene senza intervento dell'operatore.

**Giorni festivi e weekend**

Lo scheduler salta automaticamente sabato, domenica e i giorni festivi di mercato americano. Nessuna sessione viene avviata e nessuna riga appare nello storico — è il comportamento corretto.

---

### Avviare una sessione manualmente

Dalla War Room, nella sezione Scheduler, compare il pulsante **Avvia sessione**. L'operatore sceglie il tipo (mattina o EOD) e conferma.

Quando ha senso farlo:

- Una sessione automatica è saltata per un problema tecnico e l'operatore vuole recuperarla
- Si vuole forzare un ciclo fuori orario, ad esempio dopo aver corretto un errore
- Si vuole testare il sistema in un ambiente di sviluppo senza aspettare l'orario previsto

Se una sessione è già in corso, il sistema mostra un avviso e blocca il secondo avvio — bisogna aspettare il completamento prima di riprovare.

---

### Cosa può andare storto

| Situazione | Messaggio / segnale | Causa probabile | Cosa fare |
|------------|--------------------|-----------------|-----------|
| Lo scheduler non si avvia all'avvio dell'API | Badge "Inattivo", nei log compare `SESSION_SCHEDULER disabled (enabled=false in config)` | L'opzione `enabled` è `false` nel file di configurazione | Controlla `config/paper.toml`, sezione `[sessions]`: imposta `enabled = true` e riavvia l'API |
| Avvio manuale bloccato con errore | "Sessione già in corso — attendi il completamento" (codice 409) | Una sessione è già in esecuzione in background | Aspetta che la sessione corrente finisca; se il badge rimane "In esecuzione" da oltre 10 minuti, è bloccata — vedi riga seguente |
| Badge "In esecuzione" da troppo tempo | Nessun aggiornamento dopo 10+ minuti | La sessione ha raggiunto il timeout oppure è bloccata su un subprocess | Riavvia l'API: il task in background viene cancellato automaticamente allo shutdown. I log del processo sono in `logs/` |
| Avvio manuale scaduto | "Timeout sessione morning (>10 min)" (codice 504) | La sessione non ha completato entro il tempo massimo configurato | Verifica che IBKR sia raggiungibile e che non ci siano errori nei log. Ritenta dopo aver risolto il problema alla base |
| Sessione completata con avvisi | Nel log: `SESSION_MORNING WARN errors=N` | La sessione è terminata ma ha incontrato N errori non bloccanti (es. simbolo non disponibile, dati parziali) | Apri lo storico sessioni e leggi il campo `errors` della riga corrispondente. Ogni messaggio indica quale componente ha avuto problemi |
| Sessione fallita completamente | Nel log: `SESSION_MORNING FAILED` | Un errore critico ha interrotto la sessione (eccezione non gestita, servizio non raggiungibile) | Consulta i log dell'API per il dettaglio dell'eccezione. Risolvi il problema e avvia manualmente la sessione con il pulsante in UI |
| EOD senza snapshot di equity | Il grafico equity non si aggiorna, la sessione EOD risulta completata ma con warning | IBKR non era connesso al momento dell'EOD: lo snapshot di equity non può essere acquisito senza dati live dal conto | Verifica che TWS o IBG siano in esecuzione e connessi. Inserisci manualmente lo snapshot equity dal pannello Paper Metrics, poi riesegui l'EOD se necessario |
| Sessione non compare nello storico | Nessuna riga nel log per la data attesa | Giorno festivo o weekend (comportamento corretto), oppure l'API era offline all'orario previsto | Se era un giorno di mercato e l'API era attiva, controlla i log per messaggi `SESSION_SCHEDULER`. Se l'API era spenta, avvia la sessione manualmente con "Avvia sessione" |

---

### Riferimento tecnico

> Questa sezione è destinata a chi lavora direttamente con l'API o i file di configurazione.

**Endpoint**

| Operazione | Endpoint |
|------------|----------|
| Stato scheduler e prossime sessioni | `GET /opz/session/status` |
| Avvia sessione manualmente | `POST /opz/session/run` |
| Storico sessioni | `GET /opz/session/logs?profile=paper&limit=30` |

**Configurazione** — `config/paper.toml`, sezione `[sessions]`

| Campo | Default | Significato |
|-------|---------|-------------|
| `enabled` | `false` | Attiva (`true`) o disattiva lo scheduler |
| `morning_time` | `"09:00"` | Orario sessione mattutina (nel fuso configurato) |
| `eod_time` | `"16:30"` | Orario sessione serale |
| `timezone` | `"America/New_York"` | Fuso orario di riferimento |
| `duration_max_min` | `10` | Timeout massimo in minuti per sessione |
| `skip_weekends` | `true` | Salta sabato e domenica |
| `skip_holidays` | `true` | Salta giorni festivi di mercato |
| `profile` | `"paper"` | Profilo di configurazione usato dalle sessioni |

**Campi principali nello storico sessioni**

| Campo | Significato |
|-------|-------------|
| `session_type` | `"morning"` o `"eod"` |
| `regime` | Regime rilevato durante la sessione |
| `equity` | Equity del conto al termine (solo EOD) |
| `errors` | Lista di errori non bloccanti (vuota = nessun problema) |
| `trigger` | `"auto"` (scheduler) o `"manual"` (avvio manuale) |
