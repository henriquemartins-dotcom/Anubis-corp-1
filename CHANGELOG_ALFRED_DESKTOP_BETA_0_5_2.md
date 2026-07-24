# ALFRED Desktop Beta 0.5.2

## Hotfix de inicialização do executável

- Corrigida a falha `Unable to configure formatter 'default'` no executável Windows.
- Tratado o cenário em que aplicações PyInstaller sem console iniciam com `sys.stdout` e `sys.stderr` ausentes.
- Desativada a configuração padrão de logs do Uvicorn no modo desktop.
- Adicionado log próprio em `%LOCALAPPDATA%\Anubis\ALFRED\logs\alfred-desktop.log`.
- Incluído tratamento global de falhas para apresentar uma mensagem amigável em vez do traceback do PyInstaller.
- Adicionados testes de regressão para execução sem console.
