# Danza Licita IA v3

## Melhorias desta versão

- Busca nacional no PNCP: o formulário não solicita mais a UF e não envia filtro estadual à API.
- Período máximo configurado para até 10 anos (`PNCP_MAX_DATE_RANGE_DAYS=3650`).
- Períodos longos são divididos automaticamente em janelas de 30 dias (`PNCP_API_BATCH_DAYS=30`).
- A divisão não cria lacunas nem sobreposição entre as datas.
- Interface atualizada para exibir abrangência "Brasil — todos os estados".
- Testes automatizados adicionados para períodos superiores a um ano e divisão de datas.

## Observação operacional

Em buscas nacionais muito longas, o volume pode ser elevado. Use palavras-chave e ajuste "Máximo de páginas" para controlar tempo, armazenamento e quantidade de documentos baixados.
