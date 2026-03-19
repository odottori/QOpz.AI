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

### 1. Ascolta il briefing audio

Apri la WAR ROOM → clicca **▶ BRIEFING**. Il sistema ti legge:
- Regime corrente + trend
- Equity e drawdown attuali
- Exit urgenti (se presenti)
- Opportunità principali del giorno

Se il briefing non è aggiornato, clicca **GENERA** per produrne uno nuovo.

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
- **Score** — da 0 a 1, quanto il sistema lo considera buono
- **EV / Premium** — valore atteso e premio incassato
- **Kelly fraction** — sizing suggerito (solo con DATA_MODE reale)

---

### 5. Seleziona e analizza

Clicca su un candidato → i dati vengono caricati nella pipeline.

Guarda:
- **IVR** — deve essere ≥ 20 (volatilità storicamente alta → vendi volatilità)
- **Spread %** — deve essere < 10% (liquidità accettabile)
- **DTE** — tra 14 e 60 giorni
- **Score** — sopra 0.6 per considerarlo seriamente

Se qualcosa non torna, passa al candidato successivo. Il sistema ne mostra 5-10 — non sei obbligato a prendere il primo.

---

### 6. Preview e conferma

Quando hai scelto:

1. Vai in **WAR ROOM** → pannello **EXEC PREVIEW/CONFIRM**
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

## Riferimenti rapidi

| Azione | Dove |
|--------|------|
| Briefing audio | WAR ROOM → barra NARRATORE (◀ PREV / ▶ PLAY / NEXT ▶) |
| Regime corrente | Topbar, badge colorato |
| Exit urgenti | WAR ROOM → EXIT CANDIDATES |
| Scan opportunità | OPPORTUNITY → OPP SCAN |
| Preview/Confirm | WAR ROOM → EXEC PREVIEW/CONFIRM |
| Trade Log | TRADE LOG → AGGIUNGI TRADE |
| Kill Switch | Topbar, pulsante rosso |
| Stato API | Topbar → API /HEALTH |
| Guida completa | Topbar → GUIDA |
