@echo off
setlocal EnableExtensions
title HORUS CONNECTIVE - Remover monitoramento diario
schtasks /Delete /TN "Connective Horus - Monitoramento Diario" /F
if errorlevel 1 (
  echo A tarefa nao foi encontrada ou nao pode ser removida.
) else (
  echo Monitoramento diario removido do Agendador de Tarefas do Windows.
)
pause
