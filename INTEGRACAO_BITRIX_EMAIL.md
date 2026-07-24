# Configuração de notificações do Hórus Connective

## Bitrix24

1. Crie ou escolha um usuário do Bitrix24 que será o remetente das mensagens do Hórus.
2. No Bitrix24, crie um webhook de entrada com permissão para mensagens instantâneas (`im`).
3. Copie a URL completa do webhook.
4. No Hórus, abra **Notificações diárias** e cole a URL em **Webhook REST do usuário Hórus**.
5. Em **Usuários e permissões**, informe o **ID do usuário no Bitrix24** para cada responsável.
6. Use **Enviar mensagem de teste** para validar.

O Hórus utiliza o método REST `im.message.add` e envia a mensagem para o diálogo pessoal correspondente ao ID do usuário.

## E-mail

Preencha servidor, porta, usuário, senha de aplicativo, remetente e método de segurança. Para contas com autenticação em duas etapas, utilize a senha de aplicativo fornecida pelo serviço de e-mail.

## Envio com o Hórus fechado

Depois de salvar o horário, execute:

```text
AGENDAR_NOTIFICACOES_DIARIAS_WINDOWS.bat
```

O Windows criará a tarefa `Connective Horus - Notificacoes Diarias`.
