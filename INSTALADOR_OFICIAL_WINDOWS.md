# ALFRED Executive Intelligence — Instalador Oficial Windows

## Versão

Desktop Beta 0.8.1.

## Gerar o instalador

No Windows, execute com duplo clique:

```text
CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat
```

O script executa automaticamente:

1. criação de ambiente isolado de compilação;
2. instalação das dependências;
3. testes automatizados;
4. compilação do `ALFRED.exe`;
5. teste interno do executável compilado;
6. instalação do Inno Setup pelo `winget`, quando necessário;
7. criação do instalador e do hash SHA-256.

## Saída

```text
installer-output\ALFRED_Setup_0.8.1_Desktop_Beta.exe
installer-output\ALFRED_Setup_0.8.1_Desktop_Beta.sha256
```

## Atualização

O instalador utiliza um identificador estável de aplicativo. Assim, uma instalação anterior é atualizada no mesmo diretório.

Os dados do usuário não ficam dentro da pasta do programa e não são apagados durante atualização ou desinstalação:

```text
%LOCALAPPDATA%\Anubis\ALFRED
```

## Atalhos instalados

- ALFRED
- Configurações do ALFRED
- Diagnóstico do ALFRED
- Criar backup do ALFRED
- Abrir pasta de dados
