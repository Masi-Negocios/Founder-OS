"""Monta o prompt de sistema de cada agente a partir das Skills.

O prompt tem dois blocos: um estável (guia da plataforma + instruções da skill +
catálogo), que vai para o cache do provedor, e um variável (data e perfil do
negócio), que muda sem invalidar o primeiro.
"""
from __future__ import annotations

import threading

from .agentes import CONSELHO, RECEPCAO, Agente, RegistroAgentes
from .provedores import BlocoSistema
from .skills import BibliotecaSkills

GUIA_PLATAFORMA = """## Como você trabalha nesta plataforma
Você conversa com o usuário pela plataforma de agentes do Founders OS, fora dos apps do Claude. Suas instruções vêm de Skills escritas para o Claude; adapte assim:
- Ferramentas citadas nas instruções que não estão na sua lista (AskUserQuestion, artefatos e páginas publicadas, conectores, Cowork, Claude Code, execução de código) não existem aqui. Faça as perguntas em texto, respeitando o limite de perguntas das instruções, e entregue o conteúdo no chat. Para entregar um arquivo, use salvar_arquivo.
- Os arquivos da skill (references/, assets/, scripts/) não estão neste texto. Quando as instruções mandarem ler um arquivo, leia com ler_arquivo_skill antes de responder sobre o assunto dele. Caminhos no formato skill://<skill>/<arquivo> também se leem com ler_arquivo_skill.
- Quando o pedido cair no tema de uma das skills de apoio listadas abaixo, carregue as instruções dela com carregar_skill e siga-as.
- Se o pedido for de outra especialidade, ou se suas instruções mandarem passar a bola, use passar_para_agente com o agente certo e um resumo do que o usuário já contou. Para uma segunda opinião sem sair da conversa, use consultar_agente.
- Se a conversa chegou até você por passar_para_agente, continue a partir do resumo da transferência, sem repetir perguntas que já foram respondidas.
- Quando o usuário contar um fato estável do negócio (o que vende, faturamento, tamanho do time, regime tributário, cidade, público), guarde com atualizar_perfil. Use o perfil do negócio que aparece no fim deste prompt e não pergunte de novo o que já está nele.
- Responda em português do Brasil."""

GUIA_RECEPCAO = """Você é a Recepção do Founders OS: o primeiro contato do usuário com a equipe de agentes especialistas da Masi Negócios. Seu trabalho é entender o que ele precisa e passar a conversa para o agente certo, rápido.

Como agir:
- Se o pedido deixa claro qual especialista resolve, chame passar_para_agente na hora, sem responder o conteúdo você mesma. O especialista responde em seguida, na mesma conversa.
- Se o pedido ficar entre dois ou três agentes, faça uma única pergunta curta mostrando as opções pelo nome.
- Se o usuário só cumprimentar ou perguntar o que dá para fazer aqui, apresente-se em duas frases e sugira de 3 a 5 agentes, de áreas diferentes, com um exemplo de pedido para cada.
- No resumo da passagem, escreva o pedido e todo o contexto que o usuário já deu.
- Quando o usuário contar um fato estável do negócio, guarde com atualizar_perfil.
- Responda em português do Brasil, em tom direto e acolhedor."""

GUIA_CONSELHO = """Você modera o conselho de especialistas do Founders OS. Vários agentes responderam à mesma pergunta do usuário, cada um da sua área. Junte as respostas numa recomendação só, sem repetir cada uma.

Entregue, nesta ordem:
1. O que o conselho concorda (2 a 4 pontos).
2. Onde há divergência, quem pensa o quê e por quê.
3. A decisão recomendada, em uma frase, com a condição em que ela mudaria.
4. Os próximos 3 passos, com responsável e prazo sugeridos.

Cite os agentes pelo nome. Não invente número que nenhum agente trouxe. Português do Brasil, direto."""


class MontadorPrompts:
    def __init__(self, biblioteca: BibliotecaSkills, registro: RegistroAgentes) -> None:
        self.biblioteca = biblioteca
        self.registro = registro
        self._cache: dict[str, str] = {}
        self._trava = threading.Lock()

    def blocos(self, agente: Agente, perfil: dict, hoje: str) -> list[BlocoSistema]:
        return [BlocoSistema(self.estavel(agente), cache=True), BlocoSistema(self.variavel(perfil, hoje))]

    def estavel(self, agente: Agente) -> str:
        with self._trava:
            if agente.id not in self._cache:
                self._cache[agente.id] = self._montar_estavel(agente)
            return self._cache[agente.id]

    def variavel(self, perfil: dict, hoje: str) -> str:
        linhas = [f"## Contexto desta conversa", f"Data de hoje: {hoje}."]
        if perfil:
            linhas.append("Perfil do negócio (já informado pelo usuário; não pergunte de novo):")
            linhas += [f"- {chave}: {valor}" for chave, valor in sorted(perfil.items())]
        else:
            linhas.append("Perfil do negócio: ainda vazio.")
        return "\n".join(linhas)

    def _montar_estavel(self, agente: Agente) -> str:
        if agente.id == RECEPCAO:
            return GUIA_RECEPCAO + "\n\n" + self._catalogo_detalhado()
        if agente.id == CONSELHO:
            return GUIA_CONSELHO
        partes = [f'Você é o agente "{agente.nome}" do Founders OS. {agente.descricao}'.strip(), GUIA_PLATAFORMA]
        if agente.skill_principal:
            skill = self.biblioteca.obter(agente.skill_principal)
            partes.append(
                f"## Instruções da skill principal ({skill.id})\n"
                f'<skill id="{skill.id}">\n{skill.corpo.strip()}\n</skill>'
            )
            if skill.arquivos:
                partes.append("Arquivos desta skill (leia com ler_arquivo_skill quando as instruções pedirem):\n"
                              + "\n".join(f"- {a}" for a in skill.arquivos[:80]))
        apoio = [self.biblioteca.obter(s) for s in agente.skills_apoio if s in self.biblioteca and s != agente.skill_principal]
        if apoio:
            partes.append("## Skills de apoio (carregue com carregar_skill quando o tema aparecer)\n"
                          + "\n".join(f"- `{s.id}`: {_cortar(s.descricao, 400)}" for s in apoio))
        if agente.instrucoes.strip():
            partes.append("## Instruções deste agente\n" + agente.instrucoes.strip())
        destinos = self.registro.destinos_de_passagem(agente)
        if destinos:
            partes.append("## Agentes da plataforma (para passar_para_agente e consultar_agente)\n"
                          + "\n".join(f"- `{a.id}` — {a.nome}: {_cortar(a.para_que, 160)}" for a in destinos))
        return "\n\n".join(partes)

    def _catalogo_detalhado(self) -> str:
        especialistas = self.registro.especialistas()
        ordem_areas = list(self.biblioteca.areas) + sorted({a.area or "Outros" for a in especialistas} - set(self.biblioteca.areas))
        blocos = ["## Agentes disponíveis"]
        for area in ordem_areas:
            itens = [a for a in especialistas if (a.area or "Outros") == area]
            if not itens:
                continue
            blocos.append(f"### {area}")
            for a in itens:
                exemplo = f' Exemplo: "{a.exemplo}"' if a.exemplo else ""
                blocos.append(f"- `{a.id}` — {a.nome}: {_cortar(a.descricao or a.para_que, 600)}{exemplo}")
        return "\n".join(blocos)


def _cortar(texto: str, limite: int) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
