@echo off
echo Test kill WT...
taskkill /F /IM WindowsTerminal.exe 2>nul
if %errorlevel% == 0 (
    echo WT trovato e chiuso
) else (
    echo WT non trovato o errore
)
taskkill /F /IM wt.exe 2>nul
pause