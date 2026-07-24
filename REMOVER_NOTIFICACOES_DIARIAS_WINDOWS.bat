@echo off
setlocal EnableExtensions
title HORUS CONNECTIVE - Remover notificacoes diarias
schtasks /Delete /TN "Connective Horus - Notificacoes Diarias" /F
if errorlevel 1 (
  echo A tarefa nao foi encontrada ou nao pode ser removida.
) else (
  echo Notificacoes diarias removidas do Agendador de Tarefas do Windows.
)
pause
