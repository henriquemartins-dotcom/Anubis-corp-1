@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG_DIR=%LOCALAPPDATA%\Anubis\HORUS_CONNECTIVE\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\inicializacao-beta-0.13.0.log"

echo ================================================== > "%LOG_FILE%"
echo Horus Connective Desktop Beta 0.13.0 - Inicializacao >> "%LOG_FILE%"
echo Data: %date% %time% >> "%LOG_FILE%"
echo Pasta: %CD% >> "%LOG_FILE%"
echo ================================================== >> "%LOG_FILE%"

echo Preparando Horus Connective Desktop Beta 0.13.0...

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
  if not defined PY_CMD py -3.13 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.13"
  if not defined PY_CMD py -3 -c "import sys" >nul 2>nul && set "PY_CMD=py -3"
)
if not defined PY_CMD (
  where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
  echo Python nao encontrado.
  echo Instale o Python 3.12 ou 3.13 de 64 bits e marque "Add Python to PATH".
  echo Python nao encontrado. >> "%LOG_FILE%"
  pause
  exit /b 1
)

echo Python selecionado: %PY_CMD% >> "%LOG_FILE%"

if not exist .venv-desktop\Scripts\python.exe (
  echo Criando ambiente local...
  %PY_CMD% -m venv .venv-desktop >> "%LOG_FILE%" 2>&1
  if errorlevel 1 goto :error
)

call .venv-desktop\Scripts\activate.bat
if errorlevel 1 goto :error

echo Instalando ou atualizando componentes. Na primeira vez pode levar alguns minutos...
python -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error
python -m pip install -r requirements-desktop.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error

echo Abrindo o HORUS CONNECTIVE...
python -m desktop.launcher >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto :error
exit /b 0

:error
echo.
echo Nao foi possivel iniciar o Horus Connective Desktop.
echo O diagnostico foi salvo em:
echo %LOG_FILE%
echo.
echo Ultimas linhas do diagnostico:
echo --------------------------------------------------
powershell -NoProfile -Command "if (Test-Path '%LOG_FILE%') { Get-Content '%LOG_FILE%' -Tail 25 }"
echo --------------------------------------------------
pause
exit /b 1
