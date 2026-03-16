@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%1 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
exit /b 0
