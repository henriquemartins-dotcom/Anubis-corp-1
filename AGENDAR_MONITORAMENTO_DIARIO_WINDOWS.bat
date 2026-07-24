@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title HORUS CONNECTIVE - Agendar monitoramento diario

set "TASK_NAME=Connective Horus - Monitoramento Diario"
set "HORUS_EXE=%~dp0HORUS_CONNECTIVE.exe"
if not exist "%HORUS_EXE%" set "HORUS_EXE=%~dp0dist\HORUS_CONNECTIVE\HORUS_CONNECTIVE.exe"

if not exist "%HORUS_EXE%" (
  echo.
  echo O executavel HORUS_CONNECTIVE.exe nao foi encontrado.
  echo Instale o HORUS CONNECTIVE ou gere o executavel antes de criar o agendamento.
  echo.
  pause
  exit /b 1
)

set "MONITOR_TIME=%~1"
if not defined MONITOR_TIME (
  echo.
  echo Informe o horario diario no formato HH:MM.
  set /p "MONITOR_TIME=Horario [07:00]: "
)
if not defined MONITOR_TIME set "MONITOR_TIME=07:00"

echo %MONITOR_TIME%| findstr /R "^[0-2][0-9]:[0-5][0-9]$" >nul
if errorlevel 1 (
  echo Horario invalido. Use o formato HH:MM, por exemplo 07:00.
  pause
  exit /b 1
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%HORUS_EXE%\" --monitor-once" /SC DAILY /ST %MONITOR_TIME% /F
if errorlevel 1 (
  echo.
  echo Nao foi possivel criar a tarefa. Tente executar este arquivo novamente.
  pause
  exit /b 1
)

echo.
echo Monitoramento diario configurado para %MONITOR_TIME%.
echo O HORUS CONNECTIVE precisa estar com o monitoramento ATIVO na tela Monitoramento Diario.
echo A tarefa pode executar mesmo com a janela do HORUS CONNECTIVE fechada, desde que o Windows esteja ligado.
echo.
choice /C SN /N /M "Deseja testar o monitoramento agora? [S/N] "
if errorlevel 2 goto :done
"%HORUS_EXE%" --monitor-once

:done
pause
exit /b 0
