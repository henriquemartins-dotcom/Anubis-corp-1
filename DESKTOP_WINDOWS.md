# ALFRED Executive Intelligence — Desktop Beta 0.8.1

Esta edição executa o ALFRED como aplicativo local para **Windows 10/11 de 64 bits**.

## O que muda em relação à versão web

- Abre em uma janela própria, sem terminal e sem navegador manual.
- Usa banco local SQLite, sem PostgreSQL e sem Docker.
- Guarda dados em `%LOCALAPPDATA%\Anubis\ALFRED`.
- Mantém os documentos em uma pasta persistente do usuário.
- Funciona em modo de IA local mesmo sem chave da OpenAI.
- Permite cadastrar a chave da OpenAI nas configurações locais.
- Inclui backup em ZIP para a pasta `Documentos\ALFRED Backups`.
- Exige login local por senha antes de liberar o Mission Control.
- Exibe uma tela de abertura durante a inicialização.
- Centraliza os PDFs no módulo **Relatórios**.

## Teste antes de gerar o instalador

1. Instale Python 3.12 x64 no Windows.
2. Extraia o projeto em uma pasta nova.
3. Execute `TESTAR_DESKTOP_WINDOWS.bat`. Se a janela desktop não abrir, use `ABRIR_ALFRED_NAVEGADOR.bat`.
4. Na primeira execução, as dependências serão instaladas automaticamente.

O botão **Configurações** na barra lateral abre nome, usuário, senha, modo de IA e chave da API. No primeiro acesso use `henrique` / `alfred123` e altere a senha.

## Gerar o instalador no próprio Windows

1. Instale Python 3.12 x64.
2. Instale Inno Setup 6.
3. Execute `desktop\build_windows.bat`.
4. O instalador será criado em:

```text
installer-output\ALFRED_Setup_0.8.1_Desktop_Beta.exe
```

## Gerar automaticamente no GitHub

O workflow `.github/workflows/build-desktop-windows.yml` compila o aplicativo em uma máquina Windows do GitHub.

1. Envie o projeto para um repositório privado.
2. Abra **Actions** no GitHub.
3. Selecione **Build ALFRED Desktop Windows**.
4. Clique em **Run workflow**.
5. Após a conclusão, baixe o artefato `ALFRED-Desktop-Beta-0.8.1-Windows`.

Também é possível criar uma tag como `desktop-v0.8.1-beta`; nesse caso, o workflow cria uma release privada/prévia com o instalador.

## Dados locais

A desinstalação remove o programa, mas preserva os dados do usuário em:

```text
%LOCALAPPDATA%\Anubis\ALFRED
```

Essa pasta contém:

- `alfred.db`: base local de editais;
- `documents`: documentos indexados;
- `documents/reports`: checklists e relatórios PDF salvos;
- `desktop_settings.json`: configurações locais; no Windows, a chave da OpenAI é protegida pelo DPAPI do usuário.

A chave da API não é incluída nos arquivos de backup.

## Dependências de internet

O aplicativo é local, mas estas funções ainda exigem internet:

- sincronização do PNCP;
- download de editais e anexos;
- uso da OpenAI quando o modo `auto` ou `openai` estiver ativo.

A consulta a dados já armazenados, edição, exclusão e o modo de IA local continuam disponíveis no computador.

## Requisito do Windows

A janela desktop utiliza o Microsoft Edge WebView2 Runtime, normalmente já presente no Windows 10/11 atualizado. Caso a janela não abra, atualize o Edge ou instale o WebView2 Runtime da Microsoft.


## Instalador oficial

Execute `CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat` na raiz do projeto. Consulte `INSTALADOR_OFICIAL_WINDOWS.md`.
