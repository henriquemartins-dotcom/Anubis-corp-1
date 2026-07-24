# Hórus Connective Desktop Beta 0.16.0

## Gestão operacional do checklist

- Categorias do checklist agora expandem e recolhem ao clique.
- Correção visual para impedir que os itens fiquem ocultos ou comprimidos.
- Cada tarefa permite definir status, responsável cadastrado, prazo próprio e observações.
- Responsável geral da concorrência passa a ser selecionado entre os usuários ativos.
- Migração automática adiciona os novos campos ao SQLite existente.

## Alertas automáticos

- Rotina diária agenda alertas sem depender de acionamento manual.
- O alerta é disparado exatamente cinco dias antes do prazo da tarefa; quando não houver prazo próprio, usa o encerramento da concorrência.
- Recebem o alerta: administradores ativos, responsável geral da concorrência e responsável da tarefa.
- Destinatários duplicados são consolidados.
- Entrega pelos canais configurados de Bitrix24 e e-mail, com registro no histórico local.

## Instalador

- Corrigida a validação final do arquivo gerado pelo Inno Setup.
- Eliminada a mensagem falsa de erro com código 0 após compilação bem-sucedida.
