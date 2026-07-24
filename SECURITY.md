# Segurança — ALFRED Desktop Beta 0.8.1

## Escopo

Esta versão é uma beta privada para uso interno em computadores Windows autorizados.

## Acesso local

- O servidor interno escuta apenas em `127.0.0.1`.
- O aplicativo escolhe uma porta local disponível a cada execução.
- O modo desktop não publica o ALFRED na internet.
- O acesso à internet ocorre somente para PNCP, downloads externos e OpenAI quando habilitada.


## Login local

- O acesso ao Mission Control e às APIs exige usuário e senha.
- A sessão do aplicativo é temporária e não deve permanecer após o fechamento da janela Desktop.
- Há limitação de tentativas incorretas para reduzir ataques de força bruta.
- A senha é armazenada de forma protegida pelo Windows DPAPI no perfil do usuário.
- Altere a senha inicial antes de distribuir o ALFRED para outras pessoas.
- O atalho **Configurações do ALFRED** permite redefinir a senha diretamente no computador autorizado.

## Chave da OpenAI

- A chave é opcional.
- No Windows, ela é protegida com DPAPI e vinculada ao usuário local.
- A chave não é incluída nos backups criados pelo ALFRED.
- Nunca envie a chave por e-mail, WhatsApp, GitHub ou arquivos compartilhados.

## Dados

Os dados ficam em `%LOCALAPPDATA%\Anubis\ALFRED`.

Recomendações:

- mantenha o Windows protegido por senha;
- use antivírus e atualizações de segurança;
- crie backups frequentes;
- não compartilhe a pasta de dados em rede sem controle de acesso;
- revogue a chave da OpenAI se houver suspeita de comprometimento.

## Limitação da Beta

A edição desktop é destinada inicialmente a um usuário por computador. Sincronização entre vários computadores e controle multiusuário pertencem à futura edição Cloud.
