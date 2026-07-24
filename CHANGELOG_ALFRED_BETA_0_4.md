# Changelog — ALFRED Beta 0.4

## Segurança

- Adicionada tela de login administrativo.
- Rotas e APIs protegidas por sessão assinada.
- Cookie de sessão `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- Proteção CSRF nas operações de escrita.
- Limite de tentativas de login por endereço de origem.
- Bloqueio de credenciais e segredo padrão em produção.
- Documentação OpenAPI desativada em produção.
- Cabeçalhos adicionais de segurança e `noindex`.

## Operação

- Criado `render.yaml` para publicação via Blueprint.
- Configurado PostgreSQL gerenciado com `pgvector`.
- Configurado disco persistente em `/app/data`.
- Docker adaptado à variável `PORT` da hospedagem.
- Adicionado health check em `/health`.
- Criado script de backup manual do banco e dos documentos.
- Criado workflow de CI para compilação e testes.

## Produto

- Identificação visual de Beta 0.4.
- Perfil do usuário configurável por ambiente.
- Botão seguro para encerrar sessão.
- Módulos ainda indisponíveis identificados como “Em breve”.
- Controle de cache atualizado para os arquivos da versão.

## Qualidade

- 18 testes aprovados.
- JavaScript validado por análise sintática.
- Templates Jinja validados.
- Fluxo de login, sessão e logout validado por teste de integração local.
