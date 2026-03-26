@echo off
setlocal

if "%~1"=="" (
  echo usage: scripts\kill_port.bat PORT
  exit /b 2
)

if /I not "%OPZ_ALLOW_PORT_KILL%"=="1" (
  echo [DEPRECATED] scripts\kill_port.bat disabled by default.
  echo [INFO] Use scripts\opz_start_api_if_needed.bat / opz_start_ui_if_needed.bat tracked flow.
  echo [INFO] To force legacy kill set OPZ_ALLOW_PORT_KILL=1.
  exit /b 2
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%1 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
exit /b 0
