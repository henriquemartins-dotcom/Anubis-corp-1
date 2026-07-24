# ALFRED Desktop Beta 0.5.2

## Correção crítica de inicialização

- Corrigido `ModuleNotFoundError: No module named 'app'` ao iniciar por `TESTAR_DESKTOP_WINDOWS.bat`.
- O launcher agora adiciona explicitamente a raiz do projeto ao caminho de módulos.
- O arquivo BAT passou a iniciar o programa com `python -m desktop.launcher`.
- Detecção flexível de Python 3.12, Python 3.13 ou comando `python` disponível.
- Log de instalação e inicialização em `%LOCALAPPDATA%\Anubis\ALFRED\logs`.
- Mensagem de erro com as últimas linhas do diagnóstico.
- Novo modo de compatibilidade `ABRIR_ALFRED_NAVEGADOR.bat`.
