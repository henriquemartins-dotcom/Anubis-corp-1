# ALFRED Executive Intelligence - Desktop Beta 0.7.0

## Checklist inteligente

- Novo checklist operacional por edital.
- Geração com IA OpenAI quando configurada e fallback local baseado no conteúdo indexado.
- Categorias para habilitação, regularidade fiscal e trabalhista, qualificação técnica, econômico-financeira, declarações, proposta, prazos, procedimentos, garantias e amostras.
- Progresso, status, responsável, observações e referência documental.
- Acesso pela Base de Editais, Pipeline e detalhes do edital.

## Monitoramento diário

- Nova tela de configuração da rotina.
- Filtros por modalidade, UF, período e palavras-chave.
- Execução imediata ou agendada.
- Histórico dos disparos e resumo das novas concorrências.
- Modo `--monitor-once` para o Agendador de Tarefas do Windows.
- Scripts para criar e remover a tarefa diária.

## Relatórios

- Relatório PDF para as concorrências selecionadas.
- Relatório individual pelo checklist.
- Relatório automático das novidades do monitoramento.
- Visão consolidada e detalhamento por edital, incluindo pipeline e checklist.

## Desktop e distribuição

- Instalador atualizado para a versão 0.7.0.
- Inclusão do ReportLab e seus recursos no pacote PyInstaller.
- Atalhos de configuração e remoção do monitoramento diário.
- Dados mantidos em `%LOCALAPPDATA%\Anubis\ALFRED`.

## Qualidade

- 41 testes automatizados aprovados.
- JavaScript validado com `node --check`.
- Compilação Python validada.
- Relatório PDF renderizado e inspecionado visualmente.
