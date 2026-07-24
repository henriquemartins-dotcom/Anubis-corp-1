# Changelog — ALFRED Desktop Beta 0.5

## Aplicativo desktop

- Inicializador nativo baseado em pywebview.
- Servidor FastAPI local iniciado e encerrado automaticamente.
- Janela própria do ALFRED, sem necessidade de abrir terminal ou navegador.
- Porta local dinâmica e acesso restrito a `127.0.0.1`.

## Banco e documentos

- Suporte a SQLite para a edição desktop.
- Remoção da dependência obrigatória de PostgreSQL e pgvector no instalador desktop.
- Armazenamento persistente em `%LOCALAPPDATA%\Anubis\ALFRED`.
- Busca vetorial local calculada no aplicativo para bases SQLite.

## Inteligência

- Modo local disponível sem chave de API.
- Modos `auto` e `openai` configuráveis localmente.
- Janela nativa para cadastrar nome de exibição e chave da API.
- Chave da OpenAI protegida pelo Windows DPAPI no arquivo de configuração local.

## Operação

- Backup local em ZIP.
- Atalhos para configurações, backup e pasta de dados.
- Instalador Inno Setup sem necessidade de privilégios administrativos.
- Workflow GitHub Actions para gerar o instalador Windows automaticamente.
