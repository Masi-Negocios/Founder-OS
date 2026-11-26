"""Conselho: vários agentes respondem à mesma pergunta em paralelo e um moderador junta tudo."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .agentes import CONSELHO, Agente, ErroAgente
from .armazenamento import Sessao
from .orquestrador import Emissor, Orquestrador, ResultadoConversa, _nada
from .provedores import Uso

MIN_MEMBROS = 2
MAX_MEMBROS = 6
PEDIDO_MEMBRO = (
    "O usuário levou a pergunta abaixo ao conselho de especialistas do Founders OS. Responda do ponto de vista "
    "da sua especialidade, em no máximo 250 palavras: seu diagnóstico, a recomendação principal e o maior risco "
    "que você vê. Não faça perguntas de volta: se faltar dado, declare a premissa.\n\nPergunta: {pergunta}"
)


def realizar_conselho(
    orquestrador: Orquestrador,
    pergunta: str,
    *,
    agentes: list[str] | None = None,
    time: str | None = None,
    sessao_id: str | None = None,
    dono: str = "local",
    modelo: str | None = None,
    emitir: Emissor | None = None,
) -> ResultadoConversa:
    emitir = _nada if emitir is None else emitir
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise ValueError("pergunta vazia")
    modelo_sintese = None
    if time:
        definicao = orquestrador.registro.obter_time(time)
        agentes = definicao.agentes
        modelo_sintese = definicao.modelo_sintese
    ids = list(dict.fromkeys(agentes or []))
    if not MIN_MEMBROS <= len(ids) <= MAX_MEMBROS:
        raise ValueError(f"o conselho precisa de {MIN_MEMBROS} a {MAX_MEMBROS} agentes")
    membros: list[Agente] = [orquestrador.registro.obter_disponivel(a) for a in ids]

    if sessao_id:
        sessao = orquestrador.armazenamento.obter_sessao(sessao_id, dono)
        if sessao is None:
            raise ErroAgente(f"sessão não encontrada: {sessao_id}")
    else:
        sessao = orquestrador.armazenamento.criar_sessao(dono, titulo=f"Conselho: {pergunta[:60]}")
    emitir("sessao", {"sessaoId": sessao.id, "titulo": sessao.titulo})
    emitir("conselho", {"membros": [{"agente": m.id, "nome": m.nome, "area": m.area} for m in membros]})
    orquestrador.armazenamento.anexar(sessao, {"role": "user", "content": pergunta, "conselho": ids})

    trava = threading.Lock()

    def emissor_membro(agente: Agente) -> Emissor:
        def emitir_membro(tipo: str, dados: dict) -> None:
            if tipo == "texto":
                with trava:
                    emitir("membro_texto", {"agente": agente.id, "delta": dados["delta"]})
            elif tipo in ("aviso", "reinicio", "ferramenta"):
                with trava:
                    emitir(f"membro_{tipo}", {**dados, "agente": agente.id})
        return emitir_membro

    def ouvir(agente: Agente) -> tuple[Agente, ResultadoConversa]:
        sub = Sessao.efemera(dono, agente.id, sessao_pai=sessao.id)
        sub.mensagens.append({"role": "user", "content": PEDIDO_MEMBRO.format(pergunta=pergunta)})
        resultado = orquestrador._laco(sub, agente, modelo=modelo, emitir=emissor_membro(agente), profundidade=1, max_turnos=5)
        return agente, resultado

    respostas: dict[str, str] = {}
    uso = Uso()
    with ThreadPoolExecutor(max_workers=len(membros)) as executor:
        futuros = [executor.submit(ouvir, m) for m in membros]
        for futuro in as_completed(futuros):
            agente, resultado = futuro.result()
            uso.somar(resultado.uso)
            respostas[agente.id] = resultado.texto or f"(sem resposta: {resultado.erro})"
            with trava:
                emitir("membro_fim", {"agente": agente.id, "nome": agente.nome, "texto": respostas[agente.id], "erro": resultado.erro})

    moderador = Agente(
        id=CONSELHO, nome="Conselho", descricao="Modera o conselho de especialistas.", para_que="", tipo="interno", ferramentas=[],
    )
    material = "\n\n".join(f"### {m.nome} ({m.id})\n{respostas[m.id]}" for m in membros)
    sintese = Sessao.efemera(dono, CONSELHO, sessao_pai=sessao.id)
    sintese.mensagens.append({"role": "user", "content": f"Pergunta do usuário: {pergunta}\n\nRespostas do conselho:\n\n{material}"})
    emitir("agente", {"agente": CONSELHO, "nome": "Conselho", "area": None, "icone": "users", "modelo": modelo or modelo_sintese or orquestrador.config.modelo_padrao})

    def emitir_sintese(tipo: str, dados: dict) -> None:
        emitir(tipo, {**dados, "sessaoId": sessao.id} if tipo == "fim" else dados)

    resultado = orquestrador._laco(
        sintese, moderador, modelo=modelo or modelo_sintese, emitir=emitir_sintese, profundidade=1, max_turnos=2, ferramentas_permitidas=False,
    )
    uso.somar(resultado.uso)
    orquestrador.armazenamento.anexar(sessao, {
        "role": "assistant",
        "content": resultado.texto,
        "agente": CONSELHO,
        "conselho": {m.id: respostas[m.id] for m in membros},
    })
    return ResultadoConversa(sessao_id=sessao.id, agente=CONSELHO, texto=resultado.texto, uso=uso, erro=resultado.erro)
