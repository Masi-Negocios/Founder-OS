"""Agentes: cada skill vira um agente, e a configuração cria agentes compostos e times.

Um agente é uma skill principal (as instruções que ele segue) + skills de apoio
(que ele carrega quando o tema aparece) + modelo, esforço, ferramentas e para
quem ele pode passar a conversa.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .config import Config
from .skills import BibliotecaSkills, normalizar

RECEPCAO = "recepcao"
CONSELHO = "conselho"
FERRAMENTAS_PADRAO = (
    "ler_arquivo_skill",
    "listar_arquivos_skill",
    "carregar_skill",
    "passar_para_agente",
    "consultar_agente",
    "atualizar_perfil",
    "salvar_arquivo",
    "executar_script",
)


@dataclass
class Agente:
    id: str
    nome: str
    descricao: str
    para_que: str
    area: str | None = None
    icone: str | None = None
    exemplo: str | None = None
    skill_principal: str | None = None
    skills_apoio: list[str] = field(default_factory=list)
    instrucoes: str = ""
    modelo: str | None = None
    modelos_reserva: list[str] = field(default_factory=list)
    esforco: str | None = None
    passa_para: list[str] | None = None  # None = qualquer agente
    ferramentas: list[str] | None = None  # None = FERRAMENTAS_PADRAO
    max_turnos: int | None = None
    tipo: str = "skill"  # skill | composto | interno
    disponivel: bool = True
    motivo_indisponivel: str | None = None

    @property
    def skills(self) -> list[str]:
        return ([self.skill_principal] if self.skill_principal else []) + [s for s in self.skills_apoio if s != self.skill_principal]

    def publico(self, modelo_efetivo: str | None = None) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "area": self.area,
            "icone": self.icone,
            "paraQue": self.para_que,
            "exemplo": self.exemplo,
            "descricao": self.descricao,
            "tipo": self.tipo,
            "skillPrincipal": self.skill_principal,
            "skillsApoio": self.skills_apoio,
            "modelo": modelo_efetivo or self.modelo,
            "esforco": self.esforco,
            "passaPara": self.passa_para,
            "disponivel": self.disponivel,
            "motivoIndisponivel": self.motivo_indisponivel,
        }


@dataclass
class Time:
    id: str
    nome: str
    agentes: list[str]
    descricao: str = ""
    modelo_sintese: str | None = None

    def publico(self) -> dict:
        return {"id": self.id, "nome": self.nome, "descricao": self.descricao, "agentes": self.agentes}


class ErroAgente(Exception):
    pass


class RegistroAgentes:
    def __init__(self, biblioteca: BibliotecaSkills, config: Config) -> None:
        self.biblioteca = biblioteca
        self.config = config
        self.avisos: list[str] = []
        self._agentes: dict[str, Agente] = {}
        self._times: dict[str, Time] = {}
        self._montar()

    # -- montagem ---------------------------------------------------------
    def _montar(self) -> None:
        self._agentes[RECEPCAO] = Agente(
            id=RECEPCAO,
            nome="Recepção",
            descricao="Entende o pedido e passa a conversa para o agente especialista certo.",
            para_que="Não sabe com quem falar? Conte o que precisa e a Recepção chama o especialista.",
            area=None,
            icone="door-open",
            exemplo="Meu caixa não fecha e eu não sei por onde começar.",
            ferramentas=["passar_para_agente", "atualizar_perfil"],
            tipo="interno",
        )
        if self.config.agentes_automaticos:
            for skill in self.biblioteca:
                if skill.id in self.config.excluir_skills:
                    continue
                agente = Agente(
                    id=skill.id,
                    nome=skill.nome,
                    descricao=skill.descricao,
                    para_que=skill.para_que,
                    area=skill.area,
                    icone=skill.icone,
                    exemplo=skill.exemplo,
                    skill_principal=skill.id,
                )
                exige = skill.onde or ("Claude Code" if skill.compatibilidade and "claude code" in skill.compatibilidade.lower() else None)
                if exige and not self.config.permitir_so_claude_code:
                    agente.disponivel = False
                    agente.motivo_indisponivel = f"Precisa de um ambiente que a camada de agentes não oferece ({exige.rstrip('.')})."
                self._agentes[skill.id] = agente
        for bruto in self.config.agentes:
            self._aplicar_agente_config(bruto)
        for bruto in self.config.times:
            self._aplicar_time_config(bruto)

    def _aplicar_agente_config(self, bruto: dict) -> None:
        aid = str(bruto.get("id") or "").strip()
        if not aid or aid in (RECEPCAO, CONSELHO):
            self.avisos.append(f"agente sem id ou com id reservado: {bruto!r}")
            return
        base = self._agentes.get(aid)
        principal = bruto.get("skill_principal") or (base.skill_principal if base else None)
        skill = self.biblioteca.obter(principal) if principal and principal in self.biblioteca else None
        if base is None:
            base = Agente(
                id=aid,
                nome=bruto.get("nome") or (skill.nome if skill else aid),
                descricao=bruto.get("descricao") or (skill.descricao if skill else ""),
                para_que=bruto.get("para_que") or (skill.para_que if skill else ""),
                area=bruto.get("area") or (skill.area if skill else None),
                icone=bruto.get("icone") or (skill.icone if skill else None),
                exemplo=bruto.get("exemplo") or (skill.exemplo if skill else None),
                skill_principal=principal,
                tipo="composto",
            )
        mudancas = {}
        for chave_toml, atributo in (
            ("nome", "nome"), ("descricao", "descricao"), ("para_que", "para_que"), ("area", "area"),
            ("icone", "icone"), ("exemplo", "exemplo"), ("skill_principal", "skill_principal"),
            ("skills_apoio", "skills_apoio"), ("instrucoes", "instrucoes"), ("modelo", "modelo"),
            ("modelos_reserva", "modelos_reserva"), ("esforco", "esforco"), ("passa_para", "passa_para"),
            ("ferramentas", "ferramentas"), ("max_turnos", "max_turnos"),
        ):
            if chave_toml in bruto:
                mudancas[atributo] = bruto[chave_toml]
        agente = replace(base, **mudancas)
        faltando = [s for s in agente.skills if s not in self.biblioteca]
        if faltando:
            agente.disponivel = False
            agente.motivo_indisponivel = f"skills não encontradas: {', '.join(faltando)}"
            self.avisos.append(f"agente {aid}: {agente.motivo_indisponivel}")
        if agente.ferramentas is not None:
            desconhecidas = [f for f in agente.ferramentas if f not in FERRAMENTAS_PADRAO]
            if desconhecidas:
                self.avisos.append(f"agente {aid}: ferramentas desconhecidas ignoradas: {', '.join(desconhecidas)}")
                agente.ferramentas = [f for f in agente.ferramentas if f in FERRAMENTAS_PADRAO]
        if bruto.get("desativado"):
            agente.disponivel = False
            agente.motivo_indisponivel = "desativado na configuração"
        self._agentes[aid] = agente

    def _aplicar_time_config(self, bruto: dict) -> None:
        tid = str(bruto.get("id") or "").strip()
        membros = [str(a) for a in bruto.get("agentes", [])]
        desconhecidos = [a for a in membros if a not in self._agentes]
        if not tid or len(membros) < 2:
            self.avisos.append(f"time precisa de id e de pelo menos 2 agentes: {bruto!r}")
            return
        if desconhecidos:
            self.avisos.append(f"time {tid}: agentes desconhecidos ignorados: {', '.join(desconhecidos)}")
            membros = [a for a in membros if a in self._agentes]
        self._times[tid] = Time(
            id=tid,
            nome=bruto.get("nome") or tid,
            agentes=membros,
            descricao=bruto.get("descricao", ""),
            modelo_sintese=bruto.get("modelo_sintese"),
        )

    # -- consulta ---------------------------------------------------------
    def obter(self, aid: str) -> Agente:
        try:
            return self._agentes[aid]
        except KeyError:
            raise ErroAgente(f"agente não encontrado: {aid}") from None

    def obter_disponivel(self, aid: str) -> Agente:
        agente = self.obter(aid)
        if not agente.disponivel:
            raise ErroAgente(f"agente {aid} indisponível: {agente.motivo_indisponivel}")
        return agente

    def __contains__(self, aid: object) -> bool:
        return aid in self._agentes

    def listar(self, incluir_indisponiveis: bool = True) -> list[Agente]:
        return [a for a in self._agentes.values() if incluir_indisponiveis or a.disponivel]

    def especialistas(self) -> list[Agente]:
        return [a for a in self._agentes.values() if a.disponivel and a.tipo != "interno"]

    def destinos_de_passagem(self, agente: Agente) -> list[Agente]:
        candidatos = [a for a in self.especialistas() if a.id != agente.id]
        if agente.id != RECEPCAO:
            candidatos.append(self._agentes[RECEPCAO])
        if agente.passa_para is not None:
            permitidos = set(agente.passa_para) | {RECEPCAO}
            candidatos = [a for a in candidatos if a.id in permitidos]
        return candidatos

    @property
    def times(self) -> list[Time]:
        return list(self._times.values())

    def obter_time(self, tid: str) -> Time:
        try:
            return self._times[tid]
        except KeyError:
            raise ErroAgente(f"time não encontrado: {tid}") from None

    def buscar(self, texto: str) -> list[Agente]:
        alvo = normalizar(texto)
        return [a for a in self.especialistas() if alvo in normalizar(f"{a.id} {a.nome} {a.para_que}")]
