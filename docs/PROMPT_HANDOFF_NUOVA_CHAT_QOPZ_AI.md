# QOpz.AI — handoff pulito per nuova chat

## File 1 — Prompt master

**Nome file consigliato:** `PROMPT_HANDOFF_NUOVA_CHAT_QOPZ_AI.md`
**Path completo consigliato:** `C:\.dev\QOpz.AI\PROMPT_HANDOFF_NUOVA_CHAT_QOPZ_AI.md`

### Contenuto del file

```md
# PROMPT HANDOFF — QOpz.AI

Sto allegando la baseline reale del progetto QOpz.AI, già copiata localmente e ripulita in modo conservativo per ridurre il peso dello zip ed eliminare solo il materiale non essenziale al runtime o palesemente derivato/storico.

## Root locale di riferimento

`C:\.dev\QOpz.AI`

## Obiettivo operativo

Ripartire da una baseline pulita e ordinata del progetto, trattandola come **source of truth**.

Il lavoro richiesto è questo, in ordine:

1. **Aprire e ispezionare la repo reale allegata**.
2. **Classificare i file/cartelle** in:
   - core
   - support/tooling
   - demo/legacy
   - quarantine
   - delete now
3. **Verificare lo stato reale del progetto**:
   - backend
   - frontend
   - test
   - database / riallineamento DB a ogni run
4. **Provare l'applicazione come farebbe un utente reale**:
   - non solo correttezza tecnica
   - ma anche coerenza funzionale e algoritmica rispetto allo scopo dello strumento
5. **Valutare la UI sul piano della usabilità funzionale**:
   - riduzione passaggi inutili
   - migliore qualificazione delle informazioni
   - coerenza tra pannelli
   - chiarezza delle provenance e dello stato
6. **Correggere i bug reali trovati**, un delta coerente alla volta.
7. **Preparare patch progressive testate** da applicare in sovrascrittura sulla root locale.

## Vincoli e preferenze da rispettare

- root locale principale: `C:\.dev\QOpz.AI`
- niente dati sintetici / mock, salvo richiesta esplicita
- il sistema dovrebbe riallineare il DB ad ogni run
- materiale dubbio: **quarantena fino al run**
- materiale palesemente inutile o derivato: eliminazione immediata
- alleggerire e razionalizzare anche la root, quando sicuro
- ogni patch deve essere **già testata in sandbox** prima della consegna
- evitare patch cosmetiche o di cortesia
- concentrarsi su delta reali e verificabili

## Naming patch

Usare naming di questo tipo:

`OOZ_<patchnum>_<data>_<ora>.zip`

Esempio:

`OOZ_001_20260310_1530.zip`

## Stato storico noto da tenere presente

In una sessione precedente si è lavorato su una serie di delta successivi, ma i download dei pacchetti si sono guastati dopo una certa patch, quindi **non bisogna assumere come fisicamente presenti** tutti i pacchetti successivi.

Occorre quindi:
- trattare la repo allegata come baseline reale
- verificare ciò che è davvero nel codice
- non dare per scontato nulla che non sia confermato dal repo o dai test

## Materiale allegato atteso

1. zip della repo locale QOpz.AI pulita
2. file settings reale IBKR/TWS
3. documento architetturale Opportunity / OPZ integrato
4. eventuali note operative aggiuntive

## Aspettative sul metodo di lavoro

Voglio un approccio rigoroso e non superficiale.

Mi aspetto che tu:
- legga il repo vero
- faccia audit tecnico e funzionale
- verifichi il ruolo di ogni funzione rispetto allo scopo del sistema
- identifichi incoerenze di flusso operatore
- evidenzi bug, rischi, sovrastrutture inutili, colli di bottiglia UI
- proponga e implementi fix reali
- testi tutto quello che consegni

## Output attesi

Per ogni step importante:
- stato reale
- problemi trovati
- cosa è core / quarantena / delete now
- prossima azione sicura

Per ogni patch:
- nome patch
- cosa cambia
- file toccati
- test eseguiti
- esito dei test

## Direzione progettuale importante

Il progetto deve convergere verso un sistema unico che integri:
- la parte già presente in QOpz.AI
- l'estensione Opportunity Scanner / OPZ
- una corretta gestione delle option chains

La gestione option chain deve essere trattata in modo serio e coerente con il broker reale, evitando di costruire logiche inutilmente sintetiche se i dati/greche/IV possono e devono provenire dalla fonte reale.

## Regola finale

Prima stabilizza e chiarisci il progetto reale.
Poi estendi.
Non mischiare redesign profondo e baseline instabile.
```

---

## File 2 — Script PowerShell di alleggerimento conservativo

**Nome file consigliato:** `Prepare_QOpzAI_Handoff.ps1`
**Path completo consigliato:** `C:\.dev\QOpz.AI\Prepare_QOpzAI_Handoff.ps1`

### Contenuto del file

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Log {
    param([string]$Message)
    Write-Host $Message
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Remove-IfExists {
    param(
        [string]$Path,
        [switch]$Recurse
    )

    if (Test-Path -LiteralPath $Path) {
        if ($WhatIf) {
            Write-Log "[WhatIf] REMOVE $Path"
        }
        else {
            if ($Recurse) {
                Remove-Item -LiteralPath $Path -Recurse -Force
            }
            else {
                Remove-Item -LiteralPath $Path -Force
            }
            Write-Log "[OK] Removed $Path"
        }
    }
}

function Move-ToQuarantine {
    param(
        [string]$Path,
        [string]$QuarantineRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $leaf = Split-Path -Leaf $Path
    $dest = Join-Path $QuarantineRoot $leaf

    if ($WhatIf) {
        Write-Log "[WhatIf] MOVE $Path -> $dest"
    }
    else {
        Move-Item -LiteralPath $Path -Destination $dest -Force
        Write-Log "[OK] Moved $Path -> $dest"
    }
}

$Root = (Resolve-Path -LiteralPath $Root).Path
$Parent = Split-Path -Parent $Root
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$QuarantineRoot = Join-Path $Parent ("QOpz.AI_QUARANTINE_" + $Stamp)

if (-not $WhatIf) {
    Ensure-Directory -Path $QuarantineRoot
}

Write-Log "Root: $Root"
Write-Log "Quarantine: $QuarantineRoot"
Write-Log "Mode: $([string]::new('EXECUTE','WHATIF')[$WhatIf.IsPresent])"

# 1) Trash ad alta confidenza
Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('__pycache__', '.pytest_cache', 'node_modules', 'dist') } |
    ForEach-Object {
        $full = $_.FullName
        if ($full -like '*\\.git\\*') { return }
        if ($full -like '*\\.venv\\*') { return }
        Remove-IfExists -Path $full -Recurse
    }

Get-ChildItem -LiteralPath $Root -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
    ForEach-Object {
        Remove-IfExists -Path $_.FullName
    }

# 2) Materiale storico / pesante da spostare fuori repo
$CandidatesToMove = @(
    (Join-Path $Root '.zip'),
    (Join-Path $Root '.baseline_artifacts_vT11_1'),
    (Join-Path $Root 'Project export html'),
    (Join-Path $Root 'Project export'),
    (Join-Path $Root 'PROMPTS_STORICI'),
    (Join-Path $Root 'OLD_PROMPTS'),
    (Join-Path $Root 'ARCHIVE')
)

foreach ($item in $CandidatesToMove) {
    Move-ToQuarantine -Path $item -QuarantineRoot $QuarantineRoot
}

# 3) File specifici pesanti/storici in root
Get-ChildItem -LiteralPath $Root -Force -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like 'PATCH_NOTES*.md' -or
        $_.Name -like '*.zip' -or
        $_.Name -like '*.html'
    } |
    ForEach-Object {
        Move-ToQuarantine -Path $_.FullName -QuarantineRoot $QuarantineRoot
    }

# 4) Pulizia contenuti runtime notoriamente derivati
foreach ($folderName in @('logs', 'reports')) {
    $folderPath = Join-Path $Root $folderName
    if (Test-Path -LiteralPath $folderPath) {
        Get-ChildItem -LiteralPath $folderPath -Force -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-IfExists -Path $_.FullName
            }
    }
}

# 5) Sommario
$SummaryPath = Join-Path $Root 'HANDOFF_PREP_SUMMARY.txt'
$summary = @()
$summary += "QOpz.AI handoff preparation"
$summary += "Root: $Root"
$summary += "Quarantine: $QuarantineRoot"
$summary += "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$summary += "Mode: $(if ($WhatIf) { 'WHATIF' } else { 'EXECUTE' })"
$summary += ""
$summary += "Note:"
$summary += "- Trash ad alta confidenza rimosso"
$summary += "- Materiale storico/pesante spostato in quarantine sibling"
$summary += "- logs/reports file puliti"
$summary += "- Verificare manualmente il contenuto della quarantine prima di eliminarlo definitivamente"

if ($WhatIf) {
    $summary | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
    Write-Log "[OK] Summary written (WhatIf) -> $SummaryPath"
}
else {
    $summary | Set-Content -LiteralPath $Summa
```
