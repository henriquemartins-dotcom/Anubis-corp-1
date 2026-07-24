# ALFRED Executive Intelligence - Desktop Beta 0.8.0

## Login protegido

- Tela de acesso específica para o aplicativo Desktop.
- Usuário local e senha obrigatória para acessar o Mission Control e as APIs.
- Sessão temporária, encerrada ao fechar o aplicativo.
- Limite de cinco tentativas incorretas dentro da janela de segurança.
- Credenciais configuráveis pelo painel local.
- Senha protegida pelo Windows DPAPI.

## Tela de abertura

- Splash screen nativa antes da abertura da interface.
- Identidade ALFRED e assinatura Anubis Corp.
- Progresso visual durante carregamento das configurações, banco local e ALFRED Core.

## Central de relatórios

- Novo módulo **Relatórios** no menu lateral.
- Biblioteca dos PDFs armazenados em `documents/reports`.
- Classificação automática entre checklist, relatório de concorrências e monitoramento.
- Pesquisa, filtros, contadores, tamanho dos arquivos, abertura e exclusão.
- Botão para abrir a pasta local dos relatórios.

## Compatibilidade

Os dados da Beta 0.7.1 são preservados em `%LOCALAPPDATA%\Anubis\ALFRED`.

Credenciais iniciais para instalações atualizadas:

- Usuário: `henrique`
- Senha: `alfred123`

Recomenda-se alterar a senha em **Configurações** no primeiro acesso.

## Qualidade

- 47 testes automatizados aprovados.
- Login, logout e rotas protegidas validados em modo Desktop.
- JavaScript validado com `node --check`.
- Aplicação compilada com `compileall`.
