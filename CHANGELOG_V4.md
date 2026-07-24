# Danza Licita IA v4.0 — Sprint 1

## Radar PNCP 2.0

- Busca nacional por padrão, sem UF obrigatória.
- Períodos longos sem o antigo limite de 31 dias.
- Divisão automática em janelas de 30 dias para a API do PNCP.
- Paginação automática por modalidade e período.
- Barra de progresso com período, modalidade, página e contadores.
- Cancelamento de sincronizações em andamento.
- Histórico das 20 sincronizações mais recentes.
- Deduplicação de registros recebidos em diferentes janelas/modalidades.
- Persistência incremental: editais existentes são atualizados e documentos já indexados não são baixados novamente.
- Busca por palavras-chave tolerante a acentos e pequenos erros de digitação.

## Compatibilidade

A versão usa as mesmas tabelas existentes no Supabase e não exige migração de banco.
