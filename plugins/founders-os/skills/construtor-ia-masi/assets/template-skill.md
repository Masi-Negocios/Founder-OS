# Template de SKILL.md para a skill do founder

Quando a rotina estabilizar e virar skill, gere a pasta `nome-da-skill/` com este `SKILL.md`. Nome em minúsculas, com hífens, sem acento. A `description` é o que ajuda o assistente a escolher a skill: diga o que ela faz e as frases que o founder usa para pedir.

```markdown
---
name: nome-da-skill
description: >-
  [O que a skill faz, em 1-2 frases, no jeito do founder.] Use quando o usuário
  disser "[frase 1]", "[frase 2]", "[frase 3]" ou anexar [tipo de arquivo] pedindo [resultado].
---

# [Nome legível da skill] — [Empresa]

## O que esta skill faz
[2-3 linhas: entrada → saída → para quem.]

## Contexto da empresa
[O mesmo bloco de contexto do Project, resumido.]

## Passo a passo
1. Peça [o insumo], se não veio anexado. Não comece sem ele.
2. [Processamento: regras numeradas, as mesmas do Project.]
3. Monte a saída no formato abaixo.
4. [Verificação: "confira se a soma bate com o total do extrato; se não bater, aponte a diferença".]
5. Termine com [a pergunta ou o próximo passo padrão].

## Formato de saída
[Esqueleto exato.]

## Regras e limites
- [O que nunca fazer.]
- [Quando perguntar em vez de assumir.]
- [O aviso fixo, se houver: "confirme com o contador...".]

## Referências
- `references/[arquivo].md` — [o que tem lá, quando ler].
```

Depois de gerar:
1. Coloque na pasta `references/` os dados longos (categorias, tabela de preços, exemplos aprovados) como arquivos `.md` ou `.csv`.
2. No Codex ou OpenCode, salve a pasta completa em `.agents/skills/` no projeto. Para o Claude com upload de skills, compacte a pasta em ZIP e use **Personalizar → Habilidades → Adicionar → Fazer upload**.
3. Abra uma conversa no projeto e peça para usar a skill pelo nome em um exemplo real.
