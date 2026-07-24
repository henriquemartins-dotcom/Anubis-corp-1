@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-desktop\Scripts\python.exe (
  echo Execute TESTAR_DESKTOP_WINDOWS.bat primeiro para instalar os componentes.
  pause
  exit /b 1
)
call .venv-desktop\Scripts\activate.bat
python -m desktop.launcher --browser
if errorlevel 1 pause
