\
    @echo off
    setlocal enabledelayedexpansion
    cd /d %~dp0

    echo OPZ_UI_DEV: START
    echo - API: http://localhost:8000
    echo - UI:  http://localhost:5173

    rem Start FastAPI in a new window
    start "OPZ FastAPI" cmd /k "cd /d %~dp0 && py -m uvicorn api.opz_api:app --reload --port 8000"

    rem Start React (Vite) in a new window
    start "OPZ React" cmd /k "cd /d %~dp0\ui && npm run dev"

    echo OPZ_UI_DEV: spawned windows.
    exit /b 0
