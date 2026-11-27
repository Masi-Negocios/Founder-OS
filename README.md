# Founders OS

Skills da Masi Negócios para o empresário usar no Claude (app, claude.ai, Cowork e Claude Code).

## Instalar no app do Claude (planos pagos)

1. Abra o Claude e vá em **Customize › Plugins**.
2. Clique em **Add › Add marketplace › Add from a repository**.
3. Cole `Masi-Negocios/Founder-OS`.
4. Em **Plugins**, clique em **Add** no **Founders OS**.
5. Teste: escreva "testar o Founders OS".

## Instalar no Claude Code

```
claude plugin marketplace add Masi-Negocios/Founder-OS
claude plugin install founders-os@founders-os
```

## As skills dos e-books (em teste)

Na versão 2.5.0 as 25 skills feitas a partir dos e-books da Biblioteca (as `guia-…`) saíram deste pacote. Elas estão em teste num pacote próprio, `Masi-Negocios/founders-os-guias`, e voltam para cá quando passarem pelo teste. Quem quiser continuar usando instala os dois: eles convivem.

## Publicar versão nova

Altere `version` em `plugins/founders-os/.claude-plugin/plugin.json` a cada release. Sem mudar a versão, quem já instalou não recebe a mudança.
