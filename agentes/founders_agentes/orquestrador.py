"""Orquestrador: o laço de cada agente (modelo → ferramentas → modelo), passagens
de conversa entre agentes, consultas entre especialistas e troca de modelo
quando um provedor falha.

Tudo o que acontece sai como evento (texto, ferramenta, passagem, aviso, erro,
fim), para a API, a linha de comando e a interface web mostrarem ao vivo.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .agentes import RECEPCAO, Agente, ErroAgente, RegistroAgentes
from .armazenamento import Armazenamento, Sessao
from .config import Config, carregar_config
from .ferramentas import CaixaFerramentas, ContextoFerramenta, Ferramenta
from .prompts import MontadorPrompts
from .provedores import CentralProvedores, ErroProvedor, OpcoesChamada, Provedor, RespostaModelo, Uso
from .skills import BibliotecaSkills

Emissor = Callable[[str, dict], None]
MAX_TITULO = 80


def _nada(_tipo: str, _dados: dict) -> None:
    return None


@dataclass
class ResultadoConversa:
    sessao_id: str
    agente: str
    texto: str
    uso: Uso = field(default_factory=Uso)
    erro: str | None = None


class Orquestrador:
    def __init__(
        self,
        config: Config,
        *,
        biblioteca: BibliotecaSkills | None = None,
        registro: RegistroAgentes | None = None,
        provedores: CentralProvedores | None = None,
        armazenamento: Armazenamento | None = None,
        provedores_extras: dict[str, Provedor] | None = None,
    ) -> None:
        self.config = config
        self.biblioteca = biblioteca or BibliotecaSkills.carregar(config.fontes_skills)
        self.registro = registro or RegistroAgentes(self.biblioteca, config)
        self.provedores = provedores or CentralProvedores(config, provedores_extras)
        self.armazenamento = armazenamento or Armazenamento(config.runtime.banco, config.runtime.pasta_arquivos)
        self.prompts = MontadorPrompts(self.biblioteca, self.registro)
        self.ferramentas = CaixaFerramentas(self)
        self._travas: dict[str, threading.Lock] = {}
        self._trava_global = threading.Lock()

    @classmethod
    def de_config(cls, caminho: str | Path | None = None, **kwargs) -> "Orquestrador":
        return cls(carregar_config(caminho), **kwargs)

    @property
    def avisos(self) -> list[str]:
        return self.biblioteca.avisos + self.registro.avisos

    # -- API pública ------------------------------------------------------
    def conversar(
        self,
        mensagem: str,
        *,
        sessao_id: str | None = None,
        agente: str | None = None,
        modelo: str | None = None,
        dono: str = "local",
        emitir: Emissor | None = None,
        criar_com_id: bool = False,
    ) -> ResultadoConversa:
        """Manda uma mensagem do usuário. Sem sessão, cria uma; sem agente, segue com o atual ou a Recepção."""
        emitir = _nada if emitir is None else emitir
        if sessao_id:
            sessao = self.armazenamento.obter_sessao(sessao_id, dono)
            if sessao is None:
                if not criar_com_id:
                    raise ErroAgente(f"sessão não encontrada: {sessao_id}")
                sessao = self.armazenamento.criar_sessao(dono, sessao_id=sessao_id)
        else:
            sessao = self.armazenamento.criar_sessao(dono)
        with self._trava_da(sessao.id):
            return self.conversar_na_sessao(sessao, mensagem, agente=agente, modelo=modelo, emitir=emitir)

    def conversar_na_sessao(
        self,
        sessao: Sessao,
        mensagem: str,
        *,
        agente: str | None = None,
        modelo: str | None = None,
        emitir: Emissor | None = None,
    ) -> ResultadoConversa:
        emitir = _nada if emitir is None else emitir
        mensagem = (mensagem or "").strip()
        if not mensagem:
            raise ValueError("mensagem vazia")
        escolhido = self._escolher_agente(sessao, agente)
        if sessao.agente_atual != escolhido.id:
            self.armazenamento.definir_agente(sessao, escolhido.id)
        if not sessao.titulo:
            self.armazenamento.definir_titulo(sessao, mensagem[:MAX_TITULO])
        emitir("sessao", {"sessaoId": sessao.id, "titulo": sessao.titulo})
        emitir("agente", self._publico(escolhido, modelo))
        self.armazenamento.anexar(sessao, {"role": "user", "content": mensagem})
        return self._laco(sessao, escolhido, modelo=modelo, emitir=emitir, profundidade=0)

    def consultar(self, ctx: ContextoFerramenta, agente_id: str, pergunta: str, contexto: str = "") -> str:
        destino = self.registro.obter_disponivel(agente_id)
        sub = Sessao.efemera(ctx.sessao.dono, destino.id, sessao_pai=ctx.sessao.id if ctx.sessao.persistente else ctx.sessao.sessao_pai)
        texto = f"Pergunta de {ctx.agente.nome}, outro agente da plataforma, para você responder como especialista:\n\n{pergunta.strip()}"
        if contexto.strip():
            texto += f"\n\nContexto do negócio:\n{contexto.strip()}"
        texto += "\n\nResponda direto ao agente, sem fazer perguntas de volta; se faltar dado, declare a premissa."
        sub.mensagens.append({"role": "user", "content": texto})
        ctx.emitir("consulta", {"de": ctx.agente.id, "para": destino.id, "nome": destino.nome, "pergunta": pergunta})
        resultado = self._laco(sub, destino, modelo=None, emitir=_sem_texto(ctx.emitir), profundidade=ctx.profundidade + 1, max_turnos=6)
        ctx.emitir("consulta_fim", {"para": destino.id, "nome": destino.nome, "ok": resultado.erro is None})
        return resultado.texto or f"({destino.nome} não respondeu: {resultado.erro})"

    def cadeia_de_modelos(self, agente: Agente, modelo: str | None) -> list[str]:
        if modelo:
            return [modelo]
        cadeia = [agente.modelo or self.config.modelo_padrao, *agente.modelos_reserva, *self.config.modelos_reserva]
        return list(dict.fromkeys(cadeia))

    def modelo_efetivo(self, agente: Agente) -> str:
        return self.cadeia_de_modelos(agente, None)[0]

    # -- laço do agente ---------------------------------------------------
    def _laco(
        self,
        sessao: Sessao,
        agente: Agente,
        *,
        modelo: str | None,
        emitir: Emissor,
        profundidade: int,
        max_turnos: int | None = None,
        evento_texto: str = "texto",
        ferramentas_permitidas: bool = True,
    ) -> ResultadoConversa:
        limite = max_turnos or agente.max_turnos or self.config.runtime.max_turnos
        uso_total = Uso()
        textos: list[str] = []
        passagens = 0
        turnos = 0
        erro = None
        while True:
            if turnos >= limite:
                emitir("aviso", {"mensagem": f"Parei depois de {limite} rodadas seguidas de ferramentas."})
                break
            turnos += 1
            ferramentas = self.ferramentas.para_agente(agente, profundidade) if ferramentas_permitidas else []
            resposta, referencia = self._chamar_modelo(sessao, agente, modelo, ferramentas, emitir, evento_texto)
            if resposta is None:
                erro = referencia
                break
            uso_total.somar(resposta.uso)
            self.armazenamento.somar_consumo(sessao, referencia, resposta.uso)
            if resposta.texto.strip():
                textos.append(resposta.texto.strip())
            self.armazenamento.anexar(sessao, {
                "role": "assistant",
                "content": resposta.texto,
                "tool_calls": [{"id": c.id, "name": c.nome, "arguments": c.argumentos or {}} for c in resposta.chamadas],
                "raw": resposta.raw,
                "agente": agente.id,
                "modelo": referencia,
            })
            if resposta.motivo_parada == "recusa":
                emitir("recusa", {"agente": agente.id, "detalhe": resposta.detalhe})
                break
            if resposta.motivo_parada == "pausa" and not resposta.chamadas:
                continue
            if not resposta.chamadas:
                if resposta.motivo_parada == "limite":
                    emitir("aviso", {"mensagem": "A resposta foi cortada pelo limite de tokens do modelo."})
                break
            destino = self._executar_chamadas(sessao, agente, resposta, ferramentas, emitir, profundidade)
            if destino is not None:
                passagens += 1
                if passagens > self.config.runtime.max_passagens:
                    emitir("aviso", {"mensagem": "Muitas passagens seguidas entre agentes; parei aqui."})
                    break
                anterior = agente
                agente = destino
                self.armazenamento.definir_agente(sessao, agente.id)
                emitir("passagem", {"de": anterior.id, "deNome": anterior.nome, **self._publico(agente, modelo)})
        emitir("fim", {"sessaoId": sessao.id, "agente": agente.id, "uso": uso_total.como_dict(), "erro": erro})
        return ResultadoConversa(sessao_id=sessao.id, agente=agente.id, texto="\n\n".join(textos), uso=uso_total, erro=erro)

    def _chamar_modelo(
        self, sessao: Sessao, agente: Agente, modelo: str | None, ferramentas: list[Ferramenta], emitir: Emissor, evento_texto: str
    ) -> tuple[RespostaModelo | None, str]:
        sistema = self.prompts.blocos(agente, self.armazenamento.obter_perfil(sessao.dono), date.today().isoformat())
        especs = [f.espec for f in ferramentas]
        cadeia = self.cadeia_de_modelos(agente, modelo)
        ultimo_erro = "nenhum modelo configurado"
        for posicao, referencia in enumerate(cadeia):
            proximo = cadeia[posicao + 1] if posicao + 1 < len(cadeia) else None
            escreveu = False

            def ao_texto(pedaco: str) -> None:
                nonlocal escreveu
                escreveu = True
                emitir(evento_texto, {"agente": agente.id, "delta": pedaco})

            try:
                provedor, nome_modelo = self.provedores.resolver(referencia)
                resposta = provedor.gerar(
                    modelo=nome_modelo,
                    sistema=sistema,
                    mensagens=sessao.mensagens,
                    ferramentas=especs,
                    opcoes=OpcoesChamada(esforco=agente.esforco or self.config.esforco_padrao, agente_id=agente.id, agente_nome=agente.nome),
                    ao_texto=ao_texto,
                )
            except ErroProvedor as exc:
                ultimo_erro = f"{referencia}: {exc}"
                if escreveu:
                    emitir("reinicio", {"agente": agente.id})
                emitir("aviso", {"mensagem": f"O modelo {referencia} falhou ({exc})." + (f" Tentando {proximo}." if proximo else "")})
                continue
            return resposta, referencia
        emitir("erro", {"mensagem": f"Nenhum modelo respondeu. Último erro: {ultimo_erro}"})
        return None, ultimo_erro

    def _executar_chamadas(
        self, sessao: Sessao, agente: Agente, resposta: RespostaModelo, ferramentas: list[Ferramenta], emitir: Emissor, profundidade: int
    ) -> Agente | None:
        ctx = ContextoFerramenta(self, sessao, agente, emitir, profundidade)
        destino: Agente | None = None
        for chamada in resposta.chamadas:
            if resposta.motivo_parada == "limite":
                conteudo, erro = "A chamada veio cortada pelo limite de tokens: refaça com um conteúdo menor.", True
                emitir("ferramenta", {"agente": agente.id, "nome": chamada.nome, "argumentos": {}, "ok": False})
            else:
                emitir("ferramenta", {"agente": agente.id, "nome": chamada.nome, "argumentos": _resumir(chamada.argumentos)})
                resultado = self.ferramentas.executar(ferramentas, ctx, chamada.nome, chamada.argumentos, chamada.erro)
                conteudo, erro = resultado.conteudo, resultado.erro
                emitir("ferramenta_fim", {"agente": agente.id, "nome": chamada.nome, "ok": not erro, "resumo": conteudo[:200]})
                if resultado.passar_para and not erro and destino is None:
                    destino = self.registro.obter(resultado.passar_para)
            self.armazenamento.anexar(sessao, {
                "role": "tool", "tool_call_id": chamada.id, "name": chamada.nome, "content": conteudo, "is_error": erro,
            })
        return destino

    # -- apoio ------------------------------------------------------------
    def _escolher_agente(self, sessao: Sessao, pedido: str | None) -> Agente:
        if pedido and pedido not in ("auto", "automatico"):
            return self.registro.obter_disponivel(pedido)
        if sessao.agente_atual and sessao.agente_atual in self.registro:
            atual = self.registro.obter(sessao.agente_atual)
            if atual.disponivel:
                return atual
        return self.registro.obter(RECEPCAO)

    def _publico(self, agente: Agente, modelo: str | None = None) -> dict:
        dados = agente.publico(modelo or self.modelo_efetivo(agente))
        return {"agente": dados["id"], "nome": dados["nome"], "area": dados["area"], "icone": dados["icone"], "modelo": dados["modelo"]}

    def _trava_da(self, sessao_id: str) -> threading.Lock:
        with self._trava_global:
            return self._travas.setdefault(sessao_id, threading.Lock())


def _sem_texto(emitir: Emissor) -> Emissor:
    def filtrado(tipo: str, dados: dict) -> None:
        if tipo in ("aviso", "arquivo"):
            emitir(tipo, dados)
    return filtrado


def _resumir(argumentos: dict | None) -> dict:
    if not argumentos:
        return {}
    resumo = {}
    for chave, valor in argumentos.items():
        texto = valor if isinstance(valor, str) else repr(valor)
        resumo[chave] = texto if len(texto) <= 160 else texto[:157] + "..."
    return resumo
