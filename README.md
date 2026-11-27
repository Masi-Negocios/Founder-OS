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

## Como a atualização chega

O pacote fica copiado no computador de quem instalou: o Claude não busca as skills no GitHub a cada uso. Versão nova chega assim:

- **Sozinha**, quando o auto-update do marketplace está ligado. Para quem adicionou pelo app do Claude ele já vem ligado. Para quem adicionou pelo terminal vem desligado: no Claude Code, `/plugin` › **Marketplaces** › `founders-os` › ligar o auto-update.
- **Na mão**, no Claude Code: `claude plugin update founders-os@founders-os`.

## Publicar versão nova

Altere `version` em `plugins/founders-os/.claude-plugin/plugin.json` a cada release. Sem mudar a versão, quem já instalou não recebe a mudança.
