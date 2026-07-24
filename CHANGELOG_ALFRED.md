# Changelog — ALFRED Executive Intelligence

## Desktop Beta 0.8.1 - Splash animada, Login e Central de Relatórios

### Adicionado
- Login local protegido por usuário e senha.
- Sessão temporária encerrada ao fechar o ALFRED.
- Alteração das credenciais nas configurações locais.
- Tela de abertura com progresso de inicialização.
- Novo módulo **Relatórios**, com biblioteca de PDFs salvos.
- Pesquisa, filtros, abertura e exclusão de relatórios.
- Botão para abrir a pasta de relatórios no Windows.
- Atalho do instalador para abrir os relatórios salvos.

### Segurança
- Senha local protegida pelo Windows DPAPI.
- Limite de tentativas de login.
- Rotas e APIs protegidas também no modo Desktop.

### Qualidade
- 47 testes automatizados aprovados.
- Fluxo de login, logout e sessão validado.
- Compilação Python e validação JavaScript concluídas.


## Alpha 0.1 — Foundation

### Adicionado
- Rebranding completo para **ALFRED Executive Intelligence**.
- Assinatura institucional **by Anubis Corp**.
- Novo **Mission Control** como tela inicial.
- **Executive Advisor** com priorização automática da melhor oportunidade carregada.
- Indicador de **Operational Health** calculado a partir da indexação e cobertura da base.
- Nova identidade visual, navegação e nomenclatura dos módulos.
- Estrutura inicial dos módulos Alfred Bid, Ask Alfred, Alfred Docs e Automações.

### Preservado
- Sincronização com o PNCP.
- Base pesquisável de editais.
- Favoritos, filtros, drawer executivo e comando rápido.
- Upload e indexação documental.
- Perguntas com IA e fontes.


## Desktop Beta 0.7.1 - Download do Checklist Operacional

### Adicionado
- Botão **Baixar checklist PDF** dentro do checklist de cada edital.
- Documento inspirado no modelo operacional fornecido pela Danza.
- Cabeçalho com fato do edital e alerta central.
- Tabela de dados do certame e resumo do andamento.
- Seções automáticas conforme as categorias criadas pela IA.
- Marcação visual de itens pendentes, em andamento, concluídos e não aplicáveis.
- Próximos passos agrupados por responsável.
- Salvamento automático em `reports/checklists` e download pelo navegador interno.

### Qualidade
- 42 testes automatizados aprovados.
- PDF renderizado e inspecionado visualmente em todas as páginas.
- Cache, executável e instalador atualizados para a versão 0.7.1.

## Desktop Beta 0.7.0 - Checklist, Monitoramento e Relatórios

### Adicionado
- Checklist inteligente gerado por edital a partir dos documentos indexados.
- Acompanhamento de status, responsável, observações e progresso do checklist.
- Monitoramento diário configurável de concorrências no PNCP.
- Execução automática pelo aplicativo ou pelo Agendador de Tarefas do Windows.
- Relatórios PDF das concorrências selecionadas e dos resultados do monitoramento.
- Atalhos e scripts para configurar ou remover o disparo diário.

### Qualidade
- 41 testes automatizados aprovados.
- Relatórios renderizados e inspecionados visualmente.
- Pacote PyInstaller atualizado com ReportLab e dados de fuso horário.
