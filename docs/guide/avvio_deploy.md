# Avvio e pubblicazione QOpz

Questa e la procedura operativa corrente. I vecchi `vm_setup.sh`,
`vm_update.sh` e `deploy_vm.sh` non vanno eseguiti sulla VM condivisa:
contengono procedure di bootstrap o deploy dell'intero stack, non un
aggiornamento isolato della sola applicazione.

## Locale Windows

1. Installare Python e Node/npm; predisporre `.venv` con
   `py tools/opz_env_setup.py --venv-name .venv --only all`.
2. Nella directory `ui`, eseguire `npm.cmd ci` se mancano le dipendenze.
3. Avviare `QOPZ_START.bat`, anche da una directory diversa dal repository.
4. Aprire `http://127.0.0.1:8173/`. La UI inoltra API e guida allo stesso
   origin; l'API ascolta solo su `127.0.0.1:8765`.
5. Per lo stato: `powershell -NoProfile -ExecutionPolicy Bypass -File
   scripts/opz_local.ps1 -Action status`.
6. Per fermare: `QOPZ_STOP.bat` oppure `stop.bat`.

I batch delegano a `scripts/opz_local.ps1`. Non occorre Windows Terminal.
Ogni avvio ricompila la UI; una build fallita restituisce errore, senza
ripiegare su un vecchio `dist`. La compilazione avviene in staging, con
timeout di 180 secondi: la directory servita non viene svuotata durante
la build. La pubblicazione ferma solo la UI gestita e conserva la build
precedente per il ripristino in caso di errore. Un secondo avvio riusa processi verificati
e sani. Gli avvii concorrenti sono serializzati: una seconda richiesta
puo ricevere errore di lock, senza creare altre istanze.

Il launcher verifica PID, istante di creazione, eseguibile, listener e
risposta HTTP. Non termina processi estranei che occupano una porta.
In caso di conflitto segnala errore: identificare il servizio, non eseguire
un kill indiscriminato. Le vecchie finestre avviate da launcher precedenti
non sono adottate automaticamente.

Log correnti: `logs/local/api.stdout.log`, `api.stderr.log`,
`ui.stdout.log`, `ui.stderr.log`, `ui-build.log`. Il nome `stderr` non
significa errore: uvicorn vi scrive anche messaggi INFO. Consultare inoltre
`/opz/system/log`, senza cancellarne il contenuto per simulare assenza di
errori. Assenza di broker/dati non equivale a prontezza al trading.
Aprire la console effettua soltanto letture: il refresh dei dati richiede
il comando esplicito dell'operatore e non cancella il log.
Anche il GET delle curve a termine legge soltanto una cache persistente:
il pannello mostra data e stato di freschezza (oltre 30 minuti: da aggiornare).
Il comando separato "Aggiorna curve IBKR" acquisisce nuovi dati; se fallisce
conserva la cache precedente e segnala l'errore. Nessuna curva mancante viene inventata.

## VM condivisa

- Origin pubblico: `http://178.104.94.34/qopz/` oppure
  `https://qopzai.duckdns.org/qopz/` (HTTP sul dominio passa a HTTPS).
- UI, asset, API e guida mantengono il prefisso `/qopz/`.
- nginx host inoltra solo quel prefisso a `127.0.0.1:8080`.
- nginx applicativo serve la build con `VITE_BASE_PATH=/qopz/` e
  `VITE_API_BASE=/qopz`, rimuove il prefisso per il backend e protegge
  l'accesso con le credenziali Basic Auth gia configurate.
- `/qopz/health` espone solo lo stato tecnico, senza autenticazione;
  UI e API operative richiedono autenticazione. Usare HTTPS per le
  credenziali: HTTP e compatibile ma non le cifra.
- FastAPI usa `OPZ_ROOT_PATH=/qopz` per redirect e URL generati.
- La porta applicativa 8080 non viene pubblicata sull'interfaccia esterna.
- Gli altri percorsi e servizi della VM non devono essere sostituiti.

Il rilascio usa una directory sorgente immutabile
`/opt/qopz/releases/<commit>`, con il progetto Compose `qopz`, i volumi
esistenti e link ai dati e a `ops` originali. Il checkout storico
`/opt/qopz` e il suo `.env` rimangono intatti, comprese le modifiche locali.
Aggiornare solo `api`, `control-plane`, `nginx` e il ponte dedicato `broker-proxy`, con `--no-deps`: non riavviare IB Gateway,
bot o applicazioni altrui. Conservare immagini e backup DB
prima del cambio, verificare `nginx -t` prima di ricaricare il proxy host.

Configurazione di integrazione: `docker/qopz-shared-location.conf`.
La presenza del file nel repository non dimostra che sia installato:
il rapporto di validazione deve riportare separatamente prove locali,
commit effettivamente distribuito e controlli remoti.

Il Gateway IB attualmente condiviso appartiene al progetto Compose
QuantLens (`app`), non a `qopz`: il controllo servizi di QOpz rifiuta
deliberatamente di avviarlo o fermarlo. Prima dell'intervento QOpz non
risolveva `ibg`: il vecchio indicatore di connessione non era una prova valida.
Il ponte TCP autorizzato collega solo la porta 4004 tra `qopz-net` e
`app_default`; non pubblica porte host, non sposta l'API nella rete del
Gateway e non riavvia il Gateway. Il Gateway verificato e in modalita paper.
La validazione non invia ordini; il ponte rimane disponibile dopo il test.
Nel profilo condiviso `CONTROL_MANAGE_IBWR=0` disabilita esplicitamente
start/stop e mostra `EXTERNAL`, anche se esiste un vecchio Gateway QOpz
spento: non puo essere riavviato per creare un login concorrente.
Il controllo Docker accetta solo container con entrambi
i label di progetto e servizio corretti; non ripiega su servizi omonimi.
Il token del control-plane e privato e obbligatorio, mai il valore comune
di esempio. Il socket Docker rimane un privilegio amministrativo interno,
non un endpoint pubblico.

Procedura del rilascio (dopo i gate e gli audit preliminari sul candidato; i due nulla osta finali richiedono anche le prove VM):

1. Trasferire un bundle Git verificato e aggiungere il worktree detached
   `/opt/qopz/releases/<commit>`, senza pulire o resettare `/opt/qopz`.
2. Dal worktree eseguire `bash scripts/vm_release_shared.sh prepare`.
   Compila immagini versionate ed esegue il preflight senza rete e con DB
   temporaneo; non sostituisce container attivi.
3. Eseguire `bash scripts/vm_release_shared.sh activate`. Rifiuta una
   sessione attiva, conserva immagini/configurazione e un backup DB
   consistente. Dopo lo stop della sola API prova lo schema su una copia
   temporanea del DB esistente, senza rete e senza montare il DB operativo;
   solo dopo cambia i servizi QOpz indicati sopra.
4. L'installer verifica che l'origin HTTP tramite IP risponda ancora 404
   su `/`, `/polyedge/` e `/quantlens/`: se trova altri servizi, si ferma
   prima di creare il vhost. Registra la baseline nel backup, modifica solo le location QOpz, valida nginx
   prima del reload e conserva un journal per il ripristino. In caso di
   errore la procedura tenta il rollback dei servizi e del proxy; il
   backup DB resta disponibile per un ripristino esplicito, non viene
   sovrascritto automaticamente su un processo vivo.
   Il reload e asincrono: il checkpoint HTTP attende al massimo 30 secondi,
   registra gli esiti e accetta soltanto una risposta 200 JSON con stato
   `ok`, mai una pagina HTML della SPA. Un mancato ready avvia il rollback.
5. Controllare il commit in `/opt/qopz/current-release.json`, le prove
   HTTP/browser e i container degli altri progetti prima di chiudere il
   rilascio. Il file runtime con le credenziali ha permessi 600 e non va
   stampato o committato.

Il rollback ricostruisce la configurazione dei container realmente in
esecuzione, non il vecchio compose del checkout storico: conserva anche
gruppi supplementari e limiti CPU/memoria/PID. Prima di ripristinare i
metadati verifica salute, immagini e configurazione dei servizi recuperati.
Se il recupero fallisce, scrive `runtime/recovery-required.json`, blocca
altri rilasci e non attesta il ritorno alla versione precedente: il solo
puntatore `current` in quel caso non e autorevole.

## Validazione

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/opz_validate_isolated.ps1`

La procedura crea una copia temporanea del codice e chiama
`tools/opz_protected_validate.py --setup --skip-vm-sync` con una copia
indipendente della venv protetta. La copia ha
database, log e dati runtime propri: alcuni test storici azzerano il DB,
quindi non eseguire la suite completa nella directory operativa con l'API
attiva. Vengono copiati solo sorgenti Git e lock planner, mai `.env` o DB.
La verifica di scope opera su un index realmente popolato nella copia.
La verifica VM e separata: nessuna chiamata remota puo essere ereditata
accidentalmente dall'ambiente del gate locale.

Prima di un commit verificare anche nell'index originale:
`py tools/planner_guard.py check --check-target index` e
`py tools/run_gates.py --skip-manifest --skip-certify`, quest'ultimo
esclusivamente nel checkout isolato. Il gate documentale e
`py tools/docs_contract_check.py`; non copre da solo ogni frase della guida.

La VM va provata con health, UI autenticata, asset, API JSON, guida,
redirect, blocco degli accessi anonimi e assenza di regressioni sugli altri
servizi. Un semplice HTTP 200, che potrebbe contenere l'HTML della SPA,
non basta come prova di una risposta API corretta.

## Obiettivi e limiti

QOpz scopre e confronta opportunita su opzioni azionarie/ETF, applica
filtri di qualita, liquidita e rischio, presenta evidenze all'operatore e
gestisce preview/conferma e tracciamento delle operazioni. Distingue dati
sintetici e dati reali, profili dev/paper/live e stato del broker.
Il completamento del planner non certifica profittabilita, dati live
disponibili o autorizzazione al trading reale. Non vengono inviati ordini
come parte dei test di avvio e deploy.
