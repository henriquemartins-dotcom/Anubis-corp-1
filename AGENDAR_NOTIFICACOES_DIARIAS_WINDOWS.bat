@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title HORUS CONNECTIVE - Agendar notificacoes diarias

set "TASK_NAME=Connective Horus - Notificacoes Diarias"
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

set "NOTIFY_TIME=%~1"
if not defined NOTIFY_TIME (
  echo.
  echo Informe o horario diario no formato HH:MM.
  set /p "NOTIFY_TIME=Horario [08:00]: "
)
if not defined NOTIFY_TIME set "NOTIFY_TIME=08:00"

echo %NOTIFY_TIME%| findstr /R "^[0-2][0-9]:[0-5][0-9]$" >nul
if errorlevel 1 (
  echo Horario invalido. Use o formato HH:MM, por exemplo 08:00.
  pause
  exit /b 1
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%HORUS_EXE%\" --notify-once" /SC DAILY /ST %NOTIFY_TIME% /F
if errorlevel 1 (
  echo.
  echo Nao foi possivel criar a tarefa. Tente executar este arquivo novamente.
  pause
  exit /b 1
)

echo.
echo Notificacoes diarias configuradas para %NOTIFY_TIME%.
echo A rotina precisa estar ATIVA na tela Notificacoes Diarias do HORUS CONNECTIVE.
echo A tarefa pode executar com a janela do sistema fechada, desde que o Windows esteja ligado.
echo.
choice /C SN /N /M "Deseja testar o envio agora? [S/N] "
if errorlevel 2 goto :done
"%HORUS_EXE%" --notify-once

:done
pause
exit /b 0
