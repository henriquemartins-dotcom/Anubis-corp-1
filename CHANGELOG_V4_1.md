# Danza Licita IA v4.1

- Retry automático para indisponibilidade temporária do PNCP.
- Backoff exponencial configurável.
- Delay mínimo entre requisições.
- Falhas isoladas não interrompem toda a sincronização.
- Checkpoint de período, modalidade e página em `failed_queries`.
- Endpoint `POST /api/jobs/{job_id}/resume`.
- Botão de retomada no histórico.
- Status `completed_with_warnings`.
- 14 testes automatizados aprovados.
