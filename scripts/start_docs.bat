@echo off
call C:\.dev\QOpz.AI\scripts\kill_port.bat 8003
cd /d C:\.dev\QOpz.AI
python -m mkdocs build --clean -q 2>nul
cd site
python -m http.server 8003
