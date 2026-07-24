# Hórus Connective Desktop Beta 0.13.0

## Build Windows reestruturado

- removida a chamada instável `collect_all("webview")`;
- removida qualquer varredura automática de submódulos do pywebview;
- definidos explicitamente os backends Windows Edge Chromium e WinForms;
- excluídos backends Linux, macOS, Qt e CEF que não são usados;
- coleta seletiva de dados do ReportLab, tzdata e PyMuPDF;
- coleta exclusiva das bibliotecas nativas do PyMuPDF;
- UPX desativado para reduzir falsos positivos e falhas com DLLs;
- metadados do executável e instalador atualizados para 0.13.0;
- teste de regressão incluído para impedir o retorno do erro do pywebview.

## Compatibilidade

- Python 3.12 x64;
- PyInstaller 6.x;
- pywebview 5.x;
- Windows 10/11 com Microsoft Edge WebView2 Runtime.

## Funcionalidades preservadas

Todos os recursos da Beta 0.12.0 permanecem, incluindo PNCP, AMUNES/LicitaMunes,
separação entre oportunidades abertas e encerradas, usuários, checklists e
notificações por Bitrix24 e e-mail.
