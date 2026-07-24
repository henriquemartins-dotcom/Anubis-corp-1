# Hórus Connective Licitações

Aplicativo desktop para monitoramento, análise, pipeline, checklist e relatórios de concorrências públicas.

## Testar no Windows
Execute `TESTAR_DESKTOP_WINDOWS.bat`.

## Criar instalador oficial
Execute `CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat`.

Saída esperada:
`installer-output\HORUS_Connective_Setup_0.9.2_Desktop_Beta.exe`

## Primeiro acesso em instalação nova
- Usuário: `henrique`
- Senha: `horus123`

Instalações migradas preservam a senha anterior.

## Dados locais
`%LOCALAPPDATA%\Anubis\HORUS_CONNECTIVE`

Na primeira abertura, o sistema copia automaticamente os dados do diretório legado `%LOCALAPPDATA%\Anubis\ALFRED`, quando existente.

## Beta 0.12.0 — checklist e notificações

Esta versão vincula cada etapa do checklist a um usuário cadastrado e permite o envio diário de pendências por Bitrix24 e e-mail. A configuração é feita pelo administrador no módulo **Notificações diárias**.
