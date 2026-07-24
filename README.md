# Hórus Connective Executive Intelligence - Desktop Beta 0.8.1

**by Anubis Corp**

O ALFRED Desktop é a edição local para Windows 10/11. Ele abre em uma janela própria, inicia o núcleo FastAPI automaticamente e utiliza banco SQLite no computador, sem exigir Docker ou PostgreSQL.

## Novidades da Beta 0.8.1

### Acesso protegido por senha

- Tela de login própria para a edição Desktop.
- Sessão local protegida e encerrada ao fechar o aplicativo.
- Limite de tentativas incorretas de acesso.
- Usuário e senha configuráveis pelo menu **Configurações**.
- Credenciais armazenadas localmente; a senha fica protegida pelo Windows DPAPI.
- Botão **Sair** disponível na barra superior.

Na primeira execução após a atualização, use:

```text
Usuário: henrique
Senha: alfred123
```

Altere a senha em **Configurações** antes de distribuir o aplicativo para outras pessoas.

### Tela de abertura

- Splash screen com identidade visual ALFRED e Anubis Corp.
- Mensagens de inicialização do banco, ALFRED Core e tela de acesso.
- Abertura automática da tela de login quando o núcleo local estiver pronto.

### Central de relatórios

- Novo módulo **Relatórios** no menu lateral.
- Listagem de todos os PDFs salvos, inclusive checklists e relatórios de concorrências.
- Pesquisa e filtros por categoria.
- Indicadores de quantidade e espaço utilizado.
- Ações para abrir ou excluir arquivos.
- Botão **Abrir pasta** para acessar diretamente:

```text
%LOCALAPPDATA%\Anubis\HORUS_CONNECTIVE\documents\reports
```

## Funcionalidades preservadas

- Mission Control executivo;
- Radar de oportunidades do PNCP;
- Pipeline de Licitações em Kanban;
- etapas, prioridades, responsáveis e histórico de movimentações;
- pesquisa, filtros e ordenação;
- base de editais com edição e exclusão;
- favoritos e priorização;
- upload e indexação de documentos;
- Ask Alfred em modo local ou com OpenAI;
- tema claro e escuro;
- configurações locais e backup.

## Testar no Windows

1. Instale o Python 3.12 x64.
2. Extraia o projeto em uma pasta nova.
3. Execute `TESTAR_DESKTOP_WINDOWS.bat`.
4. Caso a janela desktop não abra, use `ABRIR_ALFRED_NAVEGADOR.bat`.

Na primeira execução, o ambiente local será preparado. Depois, o ALFRED abrirá como aplicativo desktop.

## Monitoramento com o ALFRED fechado

Primeiro ative e salve a rotina na tela **Monitoramento**. Depois execute:

```text
AGENDAR_MONITORAMENTO_DIARIO_WINDOWS.bat
```

O arquivo registra o comando `HORUS_CONNECTIVE.exe --monitor-once` no Agendador de Tarefas do Windows. O computador precisa estar ligado e conectado à internet no horário definido.

Para remover a tarefa automática, execute:

```text
REMOVER_MONITORAMENTO_DIARIO_WINDOWS.bat
```

## Gerar o instalador `.exe`

Execute:

```text
CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat
```

O instalador será criado em:

```text
installer-output\HORUS_Connective_Setup_0.9.2_Desktop_Beta.exe
```

Também existe um workflow do GitHub Actions em `.github/workflows/build-desktop-windows.yml`.

## Dados locais

Os dados ficam fora da pasta de instalação:

```text
%LOCALAPPDATA%\Anubis\HORUS_CONNECTIVE
```

Atualizações e desinstalações não apagam automaticamente a base de editais, os documentos, os checklists ou o histórico do pipeline.

## IA

O modo padrão é `local`, sem consumo de API. Nas configurações, é possível selecionar:

- `local`: análise e resposta no computador;
- `auto`: usa OpenAI quando houver chave e volta ao modo local em caso de falha;
- `openai`: exige uma chave válida.

No Windows, a chave cadastrada é protegida pelo DPAPI do usuário e não entra nos backups.

## Testes

```bash
DATABASE_URL="sqlite+pysqlite:///:memory:" DESKTOP_MODE=true AI_MODE=local pytest -q
```

Resultado validado nesta versão: **47 testes aprovados**.

## Versão

`0.8.1-desktop-beta`
