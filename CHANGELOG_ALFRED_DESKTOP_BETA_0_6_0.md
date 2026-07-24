# ALFRED Executive Intelligence — Desktop RC 0.6.1

## Sprint: Pipeline de Licitações

### Funcionalidades implementadas
- Novo módulo **Alfred Bid — Pipeline de Licitações**.
- Quadro Kanban com oito etapas operacionais:
  1. Nova oportunidade
  2. Triagem
  3. Em análise
  4. Decisão de participação
  5. Documentação
  6. Proposta enviada
  7. Ganha
  8. Perdida / Arquivada
- Movimentação de cartões por arrastar e soltar ou pelo seletor de etapa.
- Definição de prioridade, responsável e observações internas.
- Histórico automático de movimentações e alterações.
- Filtros por texto, etapa, prioridade, responsável, UF e prazo crítico.
- Indicadores reais de novas oportunidades, análises, propostas, ganhos e valor ativo.
- Mission Control conectado aos dados reais do pipeline.
- Business Radar alimentado pelas movimentações registradas.
- Acesso rápido ao pipeline pelos cartões do Radar de Licitações e pelo detalhamento do edital.

### Banco local
- Inclusão das tabelas `bid_pipeline` e `bid_pipeline_events`.
- Bancos existentes continuam compatíveis; as novas tabelas são criadas automaticamente na primeira abertura.
- Editais antigos entram automaticamente como **Nova oportunidade** sem perda de dados.

### Qualidade
- 30 testes automatizados aprovados.
- Fluxos de API de atualização e histórico validados com SQLite.
- JavaScript validado sem erros de sintaxe.
