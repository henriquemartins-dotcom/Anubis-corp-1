# ALFRED Executive Intelligence — Alpha 0.3.1

## Ajustes na Base de Editais

### Melhorias implementadas
- Redução do tamanho das caixas de seleção na tela **Base de editais** para um visual mais limpo e proporcional.
- Inclusão da ação **Editar** em cada edital indexado.
- Inclusão da ação **Excluir** em cada edital indexado.
- Criação de modal de edição manual com os principais campos do edital:
  - título
  - órgão
  - UF
  - município
  - modalidade
  - status
  - valor estimado
  - data de encerramento
  - objeto
- Inclusão dos endpoints de API para atualização e exclusão de editais:
  - `PUT /api/editais/{edital_id}`
  - `DELETE /api/editais/{edital_id}`
- Atualização automática da interface após editar ou excluir registros.

### Observações
- Estrutura geral do sistema preservada.
- Layout principal mantido, conforme solicitado.
- Testes existentes continuam aprovados.
