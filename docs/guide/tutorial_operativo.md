# QOpz.AI — Tutorial Operativo
*Come si usa il sistema ogni giorno. Concreto, passo per passo.*

---

## Prima di iniziare

Hai bisogno di:
- Console aperta su `http://localhost:8173` (o indirizzo VM)
- API in esecuzione (`docker compose up -d` sulla VM, o `QOPZ_START.bat` in locale)
- IBKR TWS o IBG attivo se vuoi dati reali (porta 7496 paper, 7497 live)

Se l'API è online vedrai **API LIVE** verde in alto a destra. Se vedi **API DOWN**, l'API non risponde — non procedere.

---

## Routine mattutina (15 minuti)

### 1. Verifica lo scheduler e il briefing audio

Se lo scheduler è abilitato in config, la sessione morning è già partita alle 09:00 ora New York e ha preparato i dati del giorno. Puoi verificarlo in pochi secondi:

```
GET /opz/session/status
```

Se `"last_morning"` è di oggi e `"last_result.ok": true`, il sistema ha già fatto il suo lavoro. Passa direttamente al punto 2.

Se la sessione non è partita (scheduler disabilitato o API offline durante la notte), avviala manualmente:

```
POST /opz/session/run {"type": "morning", "profile": "paper"}
```

**Briefing audio**

Apri la WAR ROOM → apri il drawer **NARRATORE** → clicca **▶ PLAY**. Il sistema ti legge:
- Regime corrente + trend
- Equity e drawdown attuali
- Exit urgenti (se presenti)
- Opportunità principali del giorno

Se il briefing non è aggiornato, clicca **GENERA** nel drawer del NARRATORE (oppure chiama `POST /opz/briefing/generate`).

---

### 2. Controlla il regime

Il badge in alto a sinistra mostra il regime:

| Badge | Cosa significa | Cosa fai |
|-------|---------------|----------|
| 🟢 **NORMAL** | Mercato tranquillo | Puoi aprire nuovi trade |
| 🟡 **CAUTION** | Volatilità elevata | Solo spread stretti, sizing 50% |
| 🔴 **SHOCK** | Evento estremo | Stop nuovi trade, monitora uscite |

In SHOCK tutta l'interfaccia di trading diventa read-only. Non è un bug — è una protezione.

---

### 3. Controlla Exit Candidates

Prima di aprire nuove posizioni, guarda se ci sono **uscite urgenti** (score ≥ 5 nella sezione EXIT CANDIDATES). Le uscite hanno priorità assoluta sulle nuove aperture.

Se c'è un'uscita urgente:
1. Leggi il motivo (score, regime, DTE)
2. Apri IBKR e chiudi la posizione manualmente
3. Registra l'uscita nel TRADE LOG

---

### 4. Avvia lo scan opportunità

Vai in **OPPORTUNITY** → scheda **OPP SCAN**:

1. Simboli: lascia il default o aggiusta in base al briefing
2. Account size: il tuo capitale paper attuale
3. Clicca **RUN SCAN**

Il sistema mostra i candidati ordinati per score. Ogni candidato ha:
- **Symbol / Strategy / Expiry** — cosa stai guardando
- **Score** — da 0 a 100 (scala composita dei 4 pilastri)
- **EV / Premium** — valore atteso e premio incassato
- **Kelly fraction** — sizing suggerito (solo con DATA_MODE reale)

---

### 5. Seleziona e analizza

Clicca su un candidato → i dati vengono caricati nella pipeline.

Guarda:
- **IVR** — deve essere ≥ 20 (volatilità storicamente alta → vendi volatilità)
- **Spread %** — deve essere < 10% (liquidità accettabile)
- **DTE** — tra 14 e 60 giorni
- **Score** — almeno 60/100 per considerarlo seriamente (≥ 75/100 = alta qualità)

Se qualcosa non torna, passa al candidato successivo. Il sistema ne mostra 5-10 — non sei obbligato a prendere il primo.

---

### 6. Preview e conferma

Quando hai scelto:

1. Vai nel tab **PIPELINE** → pannello **EXEC PREVIEW/CONFIRM**
2. Verifica symbol e strategy (già precompilati dallo scan)
3. Aggiusta il payload JSON se necessario
4. Clicca **PREVIEW** → il sistema mostra l'ordine che invierebbe
5. Controlla tutto: prezzi, strike, sizing, kelly fraction
6. Se è tutto corretto: clicca **CONFIRM** (prima volta arma) → clicca di nuovo per inviare

> ⚠ Il CONFIRM è a doppio click deliberatamente. Se hai dubbi, non cliccare la seconda volta.

---

### 7. Registra nel Trade Log

Dopo l'apertura (o anche se decidi di non aprire):

Vai in **TRADE LOG** → **AGGIUNGI TRADE** → compila i campi:
- Symbol, strategy, regime_at_entry, score_at_entry
- Se stai usando Kelly: inserisci la kelly_fraction suggerita

Questa registrazione è fondamentale: è il dato che alimenta le statistiche e sblocca il Kelly nel tempo.

---

## Checklist rapida giornaliera

```
□ Briefing ascoltato
□ Regime controllato
□ Exit urgenti verificati
□ Scan eseguito
□ Candidato analizzato
□ Preview verificata
□ Trade registrato nel log
```

---

---

## Verificare i session logs del giorno

Al termine della giornata operativa (o il mattino successivo), vale la pena controllare cosa ha fatto il sistema:

```
GET /opz/session/logs?profile=paper&limit=10
```

Cosa guardare:

| Campo | Cosa cercare |
|-------|-------------|
| `session_type` | `"morning"` e `"eod"` entrambi presenti per oggi? |
| `regime` | Regime rilevato dalla sessione automatica |
| `equity` | Equity registrata a fine sessione |
| `errors` | Lista vuota = tutto OK. Se ci sono errori, leggi i messaggi |
| `trigger` | `"auto"` = avviato dallo scheduler, `"manual"` = avviato da te |

Se una sessione manca, puoi rieseguirla manualmente:

```
POST /opz/session/run {"type": "eod", "profile": "paper", "force": true}
```

---

## Situazioni speciali

### Kill Switch

Il pulsante rosso **KILL SWITCH** in alto a destra blocca immediatamente tutti gli ordini futuri. Usalo se:
- Sei in dubbio su qualcosa di grave
- Il mercato sta facendo qualcosa di inaspettato
- Vuoi staccare senza pensieri

Per riattivare: clicca di nuovo (richiede conferma).

---

### Regime cambia durante il giorno

Il regime viene aggiornato ogni 5 minuti. Se cambia:
- **NORMAL → CAUTION**: nessuna azione urgente, dimezza il sizing sui prossimi trade
- **CAUTION → SHOCK**: chiudi eventuali posizioni rischiose, no nuovi trade
- **SHOCK → NORMAL**: aspetta 1-2 giorni prima di riaprire posizioni

---

### Kelly disabilitato

Se il pannello Kelly mostra il lock, significa che il sistema non ha ancora abbastanza dati reali per calcolare la frazione ottimale. È normale nelle prime settimane. Usa sizing fisso (1-2% del capitale) finché Kelly non si sblocca.

---

### Dati IBKR non disponibili

Se IBKR non è connesso, il sistema usa dati sintetici (watermark **SYNTHETIC** visibile). In questo stato:
- Puoi fare scan e analisi
- Non aprire trade reali — i prezzi non sono affidabili

---

## Il tuo percorso paper — dove sei adesso

Il sistema è in modalità paper. Non è un limite — è la fase più importante.

### Prima settimana: manuale

Opera in manuale. Fai il ciclo completo ogni giorno (briefing → regime → scan → anteprima → conferma). L'obiettivo è imparare il flusso, non fare profitto.

### Dalla seconda settimana: Auto-Paper

Quando il ciclo ti è chiaro, attiva **Auto-Paper**. Il sistema opera da solo — scan, valutazione, apertura, chiusura. Il tuo ruolo diventa osservare il **Paper Countdown** nella WAR ROOM:

| Cosa mostra | Perché ti serve |
|-------------|-----------------|
| Operazioni chiuse su 50 | Quanto manca alla verifica |
| Rendimento/rischio, perdita massima | Le metriche convergono? |
| Regimi attraversati | Hai visto almeno un cambio di mercato? |
| Stima di quando sarai pronto | Per pianificare il passaggio al vivo |

**Ogni settimana** (10 minuti): guarda il countdown. Se il rapporto rendimento/rischio crolla o la perdita massima sale, è un segnale — non ignorarlo.

**Ogni mese** (1 ora): rivedi le metriche aggregate. Chiediti: *"Se questi fossero soldi veri, sarei sereno?"*

> Per approfondire: leggi il **Capitolo 8 — Il Periodo Paper** nella guida completa.

---

## Riferimenti rapidi

| Azione | Dove |
|--------|------|
| Briefing audio | WAR ROOM → barra NARRATORE (◀ PREV / ▶ PLAY / NEXT ▶) |
| Regime corrente | Topbar, badge colorato |
| Exit urgenti | WAR ROOM → EXIT CANDIDATES |
| Scan opportunità | OPPORTUNITY → OPP SCAN |
| Preview/Confirm | Tab PIPELINE → EXEC PREVIEW/CONFIRM |
| Trade Log | TRADE LOG → AGGIUNGI TRADE |
| Kill Switch | Topbar, pulsante rosso |
| Stato API | Topbar → API /HEALTH |
| Guida completa | Topbar → GUIDA |
| Session logs | `GET /opz/session/logs` |
| Stato scheduler | `GET /opz/session/status` |
| Sessione manuale | WAR ROOM → banner scheduler → **▶ Morning** / **▶ EOD** |
| IBWR on/off | `POST /opz/ibwr/service` |
| Observer on/off | `POST /opz/execution/observer` |
| Control plane | `GET /opz/control/status` |

---

### Manutenzione IBKR — procedura rapida

Se devi riavviare TWS/IBG o fare modifiche al conto:

```
# 1. Ferma l'esecuzione
POST /opz/ibwr/service  {"action": "off"}

# 2. Fai la manutenzione

# 3. Riattiva
POST /opz/ibwr/service             {"action": "on"}
POST /opz/execution/kill_switch    {"action": "deactivate"}
POST /opz/execution/observer       {"action": "on"}
```

Per i dettagli completi vedi il **Capitolo 10 — Il Control Plane operativo**.

---

## Se qualcosa non va — riferimento rapido

| Problema | Segnale che vedi | Causa probabile | Cosa fare |
|----------|-----------------|-----------------|-----------|
| Briefing non generato | Drawer NARRATORE vuoto o data non aggiornata | NARRATORE non attivo in configurazione, oppure sessione morning non completata o fallita | Verifica che la sessione morning sia andata a buon fine (`GET /opz/session/status`); se manca, avviala manualmente (`POST /opz/session/run {"type": "morning"}`); poi clicca GENERA nel drawer NARRATORE |
| Scanner vuoto | Lista OPP SCAN senza candidati dopo RUN SCAN | Regime SHOCK attivo (corretto e atteso), oppure tutti i simboli filtrati per IVR basso o spread eccessivo | Se il badge è SHOCK: normale, non aprire trade. Se è NORMAL: IVR di mercato probabilmente basso, attendi condizioni più favorevoli |
| Ordine non eseguito | CONFIRM eseguito ma nessuna posizione aperta in IBKR | Kill switch attivo, oppure IBWR non in esecuzione, oppure connessione IBKR caduta dopo lo scan | Controlla il Kill Switch (topbar: deve essere verde/inattivo); verifica IBWR con `GET /opz/control/status`; riattiva se necessario con `POST /opz/ibwr/service {"action": "on"}` |
| Session log mancante | `GET /opz/session/logs` non mostra la sessione del giorno | Scheduler non abilitato in configurazione, oppure API offline all'orario previsto (09:00 NY) | Verifica `GET /opz/session/status` → campo `scheduler_enabled`; se disabilitato, avvia la sessione manualmente; considera di abilitare lo scheduler per le sessioni future |
| Observer Telegram silenzioso | Nessuna notifica ricevuta su Telegram durante la sessione | Bot non configurato correttamente, token scaduto, oppure IBKR non connesso (l'Observer non invia se non c'è attività da segnalare) | Verifica la configurazione del bot in config; controlla `GET /opz/control/status` per lo stato dell'Observer; assicurati che IBKR sia connesso — l'Observer segnala solo eventi legati all'esecuzione |
