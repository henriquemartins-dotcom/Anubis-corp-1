# Hórus Connective Desktop Beta 0.12.0

## Checklist operacional redesenhado

- Modal ampliado para uso em telas desktop.
- Campos de status, conteúdo, responsável e observações separados em colunas.
- Área de observações redimensionável.
- Responsável selecionado diretamente entre os usuários ativos cadastrados.
- Identificação visual de itens obrigatórios e opcionais.
- Layout responsivo para notebooks e telas menores.

## Notificações diárias aos responsáveis

- Resumo automático das etapas pendentes e em andamento.
- Envio por mensagem privada no Bitrix24.
- Envio por e-mail via SMTP.
- Configuração exclusiva do administrador.
- Horário diário configurável.
- Envio manual e mensagem de teste.
- Histórico local de sucessos e falhas.
- Execução pelo Agendador de Tarefas do Windows mesmo com o Hórus fechado.

## Gestão de usuários

- Novo campo ID do usuário no Bitrix24.
- Preferências individuais para receber e-mail e/ou mensagem no Bitrix24.
- Responsáveis dos checklists vinculados às contas locais do Hórus.

## Banco local

- Novas configurações e históricos permanecem no SQLite local.
- Webhook do Bitrix24 e senha SMTP ficam protegidos no Windows por DPAPI.
- Migração automática das bases anteriores sem excluir editais, checklists ou usuários.
