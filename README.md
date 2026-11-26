# Founders OS

56 skills de estratégia, vendas, operações, pessoas e finanças da Masi Negócios, mais uma skill de boas-vindas. O mesmo catálogo atende Codex, Claude e OpenCode com DeepSeek.

## Começar no Codex

Com o Codex CLI instalado, execute no terminal:

```sh
codex plugin marketplace add Masi-Negocios/Founder-OS
codex plugin add founders-os@founders-os
```

Abra uma conversa no Codex e escreva `$founders-os:boas-vindas`. Para testar com uma tarefa real, tente **“Use a skill guia-dre-e-caixa do Founders OS e me ajude a montar o fluxo de caixa de 13 semanas.”**

Esse caminho instala o catálogo completo para uso pessoal. Para escolher skills ou chamar especialistas como subagentes, use a instalação por projeto abaixo. Escolha um dos dois caminhos para evitar que uma skill apareça duas vezes no seletor do Codex.

Para adicionar uma única skill à sua conta pelo próprio chat do Codex, use o instalador integrado. Exemplo:

```text
$skill-installer instale a skill desta pasta: https://github.com/Masi-Negocios/Founder-OS/tree/main/plugins/founders-os/skills/guia-dre-e-caixa
```

## Instalar skills e agentes em um projeto

Requer Git e Python 3.8 ou superior. Os comandos abaixo partem da pasta do projeto onde você trabalha. No Windows, pode usar `py -3` no lugar de `python3`.

```sh
git clone https://github.com/Masi-Negocios/Founder-OS.git
python3 Founder-OS/scripts/instalar.py
```

Abra essa mesma pasta no Codex e peça **“Use o subagente masi-financeiro para identificar quais números faltam para montar a DRE da minha loja.”** Para invocar diretamente a skill local, use `$diretor-financeiro-masinegocios`.

Se você já tem uma cópia do Founders OS em outra pasta, rode `python3 scripts/instalar.py --projeto "/caminho/do/seu/projeto"` de dentro dessa cópia. O destino é sempre a pasta de trabalho atual ou a indicada por `--projeto`.

| O que você quer | Comando na pasta do seu projeto |
| --- | --- |
| Ver os IDs das skills e os nomes dos agentes | `python3 Founder-OS/scripts/instalar.py --listar` |
| Instalar só o Diretor Financeiro e seu agente | `python3 Founder-OS/scripts/instalar.py --skill diretor-financeiro-masinegocios` |
| Instalar duas skills específicas | `python3 Founder-OS/scripts/instalar.py --skill guia-dre-e-caixa --skill guia-cac-ltv-payback` |
| Instalar para OpenCode | `python3 Founder-OS/scripts/instalar.py --ambiente opencode` |

As skills ficam em `.agents/skills/<id>/`, com suas referências, scripts e modelos. O instalador gera os perfis em `.codex/agents/` ou `.opencode/agents/`. Você pode executar a instalação para os dois ambientes no mesmo projeto. Eles compartilham as skills e cada um recebe seus perfis.

Os sete perfis são `masi-estrategia`, `masi-financeiro`, `masi-comercial`, `masi-pessoas`, `masi-head-ia`, `masi-qualidade` e `masi-agente-vendas`. Na instalação seletiva, cada perfil acompanha a skill correspondente. As cinco skills da Máquina de Carrosséis são instaladas juntas porque uma usa os recursos das outras.

## Usar com DeepSeek e outros assistentes

**OpenCode com DeepSeek.** Instale para OpenCode com o comando acima. Abra `opencode` no projeto, digite `/connect`, escolha DeepSeek e informe sua chave no próprio cliente. Selecione o modelo e peça **“Use o subagente masi-comercial para revisar meu funil de vendas.”** Os perfis herdam o modelo da sessão. O instalador só escreve arquivos locais. [Configuração oficial do DeepSeek no OpenCode](https://api-docs.deepseek.com/quick_start/agent_integrations/opencode/)

**Codex com DeepSeek.** Se você já configurou o DeepSeek como provedor do Codex, use o fluxo normal do Codex. [Configuração oficial do provedor](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)

**Chat ou API que recebe texto.** Escolha uma pasta em `plugins/founders-os/skills/`. Use o corpo de `SKILL.md` como instrução do assistente, envie seu pedido e forneça os arquivos de referência que a etapa pedir. Por exemplo, em `guia-dre-e-caixa`, anexe as referências indicadas e informe os números do negócio. Esse modo permite usar o método manualmente. A descoberta de arquivos, a execução de scripts e a delegação dependem do aplicativo.

**Recursos de produção.** A Máquina de Carrosséis entrega perfil, slides e legenda em Markdown no projeto ou na conversa. A página com revisão e ZIP requer `Artifact` e `ArtifactData`. Motion Vídeo requer terminal, Node.js, FFmpeg e Python, e algumas etapas usam recursos do macOS. Vídeos Virais entrega o roteiro e as falas e usa o conector Higgsfield para produzir o vídeo.

## Claude

No app, abra **Customize › Plugins › Add › Add marketplace › Add from a repository**, cole `Masi-Negocios/Founder-OS` e adicione **Founders OS**. Em um chat novo, peça **“testar o Founders OS”**.

No Claude Code:

```sh
claude plugin marketplace add Masi-Negocios/Founder-OS
claude plugin install founders-os@founders-os
```

## Atualizar ou remover

| Instalação | Atualizar | Remover |
| --- | --- | --- |
| Plugin do Codex | `codex plugin marketplace upgrade founders-os` e `codex plugin add founders-os@founders-os` | `codex plugin remove founders-os@founders-os` |
| Por projeto | `git -C Founder-OS pull --ff-only` e repita o comando de instalação com o mesmo ambiente e seleção | `python3 Founder-OS/scripts/instalar.py --remover` |
| Plugin do Claude | Sincronize o marketplace no app | Remova o plugin no mesmo menu |

Na instalação por projeto, `.agents/founders-os.json` registra os arquivos gerenciados. A remoção vale para os dois ambientes daquele projeto. Em caso de colisão ou edição local, o instalador informa o caminho para você preservar sua versão antes de tentar de novo.

## Manter o pacote

Edite a skill uma vez em `plugins/founders-os/skills/<id>/`. O catálogo em `catalogo.json` associa cada especialista à sua skill pelo campo `agente`. Incremente `version` em `plugins/founders-os/.claude-plugin/plugin.json` a cada release e execute:

```sh
python3 scripts/gerar.py
python3 -m unittest discover -s tests
node --test tests/jornada.test.mjs
```

O gerador atualiza o manifesto portátil do plugin, as referências compartilhadas, as boas-vindas e o catálogo do site. O teste do guia usa Node.js 22.7 ou superior. Para testar o plugin a partir de um checkout local, use `codex plugin marketplace add .` na raiz antes de instalar pelo nome.

O uso no próprio negócio segue os termos da [licença da Masi Negócios](LICENSE).
