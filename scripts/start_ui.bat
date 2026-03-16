@echo off
call C:\.dev\QOpz.AI\scripts\kill_port.bat 8173
cd /d C:\.dev\QOpz.AI\ui
node_modules\.bin\vite.cmd
