# ALFRED Executive Intelligence — Beta 0.4

## Objetivo da versão

Primeira versão preparada para disponibilização privada em ambiente online.

## Funcionalidades liberadas

- Mission Control.
- Radar de licitações e sincronização com o PNCP.
- Pesquisa, filtros e ordenação de oportunidades.
- Base de editais com seleção, edição e exclusão.
- Favoritos e priorização.
- Upload e indexação de documentos.
- Ask Alfred com recuperação de fontes.
- Histórico de sincronizações.
- Tema claro e escuro.

## Segurança e operação

- Tela de login administrativo.
- Sessão assinada em cookie `HttpOnly`.
- Cookie seguro em produção.
- Proteção CSRF para operações de escrita.
- Limite de tentativas de login.
- Rotas e APIs protegidas.
- Documentação da API desativada em produção.
- Cabeçalhos de segurança e bloqueio de indexação por buscadores.
- Verificação de configurações inseguras na inicialização.

## Publicação

- Blueprint `render.yaml`.
- PostgreSQL gerenciado com suporte a `pgvector`.
- Disco persistente para documentos.
- Health check em `/health`.
- Docker preparado para a porta fornecida pela hospedagem.
- Workflow de testes no GitHub Actions.
- Script de backup manual.

## Limitações conhecidas da beta

- Existe um único usuário administrativo configurado por variáveis de ambiente.
- Integrações e Configurações aparecem como módulos futuros.
- A aplicação usa uma única instância quando o disco persistente está anexado.
- Não há painel de gestão de usuários ou permissões nesta versão.
- Alterações estruturais de banco ainda utilizam criação automática de tabelas; migrações versionadas entrarão em sprint futura.
