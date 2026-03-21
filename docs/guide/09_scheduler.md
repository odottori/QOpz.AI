# Capitolo 9 — Il Session Scheduler
## Sessioni automatiche mattutine e serali

---

### Cos'è il Session Scheduler

Il Session Scheduler è il componente che avvia automaticamente due cicli operativi ogni giorno di trading:

- **Sessione Morning** — alle 09:00 ora New York, prima dell'apertura del mercato americano. Esegue il regime check, lo scan delle opportunità e prepara il briefing del giorno.
- **Sessione EOD** (End of Day) — alle 16:30 ora New York, dopo la chiusura. Aggiorna le metriche di equity, controlla le posizioni aperte, registra l'esito della giornata.

Senza lo scheduler, queste operazioni vanno avviate manualmente ogni giorno. Con lo scheduler attivo, il sistema lavora da solo nei giorni di mercato — incluso nei fine settimana di raccolta dati.

---

### Come si attiva

Lo scheduler si configura nel file `config/paper.toml` (o `config/dev.toml` per sviluppo), nella sezione `[sessions]`:

```toml
[sessions]
enabled = true
morning_time = "09:00"
eod_time = "16:30"
timezone = "America/New_York"
duration_max_min = 10
skip_weekends = true
skip_holidays = true
profile = "paper"
api_base = "http://localhost:8765"
```

I campi principali:

| Campo | Default | Significato |
|-------|---------|-------------|
| `enabled` | `false` | Attiva (`true`) o disattiva lo scheduler |
| `morning_time` | `"09:00"` | Orario sessione mattutina (timezone locale) |
| `eod_time` | `"16:30"` | Orario sessione serale |
| `timezone` | `"America/New_York"` | Fuso orario di riferimento |
| `duration_max_min` | `10` | Timeout massimo in minuti per sessione |
| `skip_weekends` | `true` | Salta sabato e domenica |
| `skip_holidays` | `true` | Salta giorni festivi di mercato |
| `profile` | `"paper"` | Profilo di configurazione usato dalle sessioni |

Lo scheduler si avvia automaticamente all'apertura dell'API. Se `enabled = false`, rimane inattivo ma disponibile per trigger manuali.

---

### Flusso: automatico vs manuale

**Automatico (scheduler abilitato)**

```
API avviata
    └─ Scheduler legge config
       └─ Calcola prossima sessione (morning o eod)
          └─ Dorme fino all'orario previsto
             └─ Esegue session_runner.py come subprocess
                └─ Salva risultato in DuckDB (tabella session_logs)
                   └─ Ricomincia il ciclo
```

**Manuale (trigger on-demand)**

Puoi avviare una sessione in qualsiasi momento anche con lo scheduler disabilitato, tramite l'API:

```
POST /opz/session/run
{
  "type": "morning",   // oppure "eod"
  "profile": "paper",
  "force": false        // true = esegui anche fuori orario/giorno di trading
}
```

Il trigger manuale è utile per:
- Recuperare una sessione saltata per problemi tecnici
- Testare il sistema fuori orario
- Forzare un ciclo dopo aver corretto un errore

> Se una sessione è già in corso, il sistema risponde con errore 409 — attendi il completamento prima di rilanciare.

---

### Stato dello scheduler

Per vedere se lo scheduler è attivo e quando sono previste le prossime sessioni:

```
GET /opz/session/status
```

Risposta tipica:

```json
{
  "ok": true,
  "enabled": true,
  "running": false,
  "last_morning": "2026-03-21T13:02:17Z",
  "last_eod": "2026-03-20T20:31:44Z",
  "next_morning": "2026-03-24T13:00:00Z",
  "next_eod": "2026-03-24T20:30:00Z",
  "last_result": { "ok": true, "regime": "NORMAL", ... }
}
```

| Campo | Significato |
|-------|-------------|
| `enabled` | Se lo scheduler è abilitato in config |
| `running` | Se una sessione è in esecuzione in questo momento |
| `last_morning` / `last_eod` | Timestamp ISO dell'ultima esecuzione (UTC) |
| `next_morning` / `next_eod` | Timestamp ISO della prossima esecuzione prevista |
| `last_result` | Esito dell'ultima sessione completata |

---

### Come leggere i session logs

Ogni sessione completata viene registrata nella tabella `session_logs` di DuckDB. Per consultare lo storico:

```
GET /opz/session/logs?profile=paper&limit=30
```

Parametri opzionali:
- `limit` — numero di righe restituite (default: 30, max: 200)
- `session_type` — filtra per `"morning"` o `"eod"`

Ogni riga del log contiene:

| Campo | Tipo | Significato |
|-------|------|-------------|
| `log_id` | string | Identificatore univoco della sessione |
| `session_date` | string | Data della sessione (YYYY-MM-DD) |
| `session_type` | string | `"morning"` o `"eod"` |
| `regime` | string | Regime rilevato durante la sessione (NORMAL/CAUTION/SHOCK) |
| `equity` | float | Equity del conto al termine della sessione |
| `n_symbols` | int | Numero di simboli scansionati |
| `errors` | lista | Errori non bloccanti incontrati (lista di stringhe) |
| `trigger` | string | `"auto"` (scheduler) o `"manual"` (trigger manuale) |
| `started_at` | string | Timestamp inizio sessione (ISO UTC) |
| `finished_at` | string | Timestamp fine sessione (ISO UTC) |

---

### Troubleshooting

**Lo scheduler non si avvia**

Verifica che in `config/paper.toml` sia presente `enabled = true` nella sezione `[sessions]`. Controlla i log dell'API per righe che iniziano con `SESSION_SCHEDULER`.

**Una sessione non compare nei logs**

La sessione potrebbe essere stata saltata per una di queste ragioni:
- Giorno festivo o weekend (con `skip_weekends = true` / `skip_holidays = true`)
- La sessione è scaduta per timeout (campo `duration_max_min`)
- L'API era offline all'orario previsto

**Una sessione mostra errori nel campo `errors`**

Gli errori nel campo `errors` sono non bloccanti — la sessione è comunque considerata completata. Leggi i messaggi per capire quale componente ha avuto problemi (es. connessione IBKR, dati mancanti).

**Voglio rieseguire una sessione fallita**

```
POST /opz/session/run
{
  "type": "morning",
  "profile": "paper",
  "force": true
}
```

Il parametro `"force": true` permette di eseguire la sessione anche se non è il giorno o l'orario previsto.

**Lo scheduler mostra `"running": true` da troppo tempo**

La sessione è bloccata. Riavvia l'API — il task in background viene cancellato e pulito automaticamente allo shutdown. I log del subprocess sono nella cartella `logs/`.
