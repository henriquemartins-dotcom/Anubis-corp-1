@echo off
setlocal
cd /d "%~dp0"
if not exist .venv-desktop (
  echo Execute TESTAR_DESKTOP_WINDOWS.bat pelo menos uma vez antes de configurar.
  pause
  exit /b 1
)
call .venv-desktop\Scripts\activate.bat
python desktop\launcher.py --config
