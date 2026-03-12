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
Write-Log "Mode: $(if ($WhatIf) { 'WHATIF' } else { 'EXECUTE' })"

# 1) Trash ad alta confidenza
Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('__pycache__', '.pytest_cache', 'node_modules', 'dist') } |
    ForEach-Object {
        $full = $_.FullName
        if ($full -like '*\\.git\\*') { return }
        if ($full -like '*\\.venv\\*') { return }
        Remove-IfExists -Path $full -Recurse
    }
Write-Log "Done."