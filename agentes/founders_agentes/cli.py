"""Linha de comando: python -m founders_agentes <comando>."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .agentes import RECEPCAO
from .config import ErroConfig, carregar_config
from .orquestrador import Orquestrador

CINZA = "\033[2m"
NEGRITO = "\033[1m"
NORMAL = "\033[0m"


def _cor(texto: str, estilo: str) -> str:
    return f"{estilo}{texto}{NORMAL}" if sys.stdout.isatty() else texto


def _emissor_terminal():
    estado = {"agente": None}

    def emitir(tipo: str, dados: dict) -> None:
        if tipo == "agente" and dados["agente"] != estado["agente"]:
            estado["agente"] = dados["agente"]
            print(_cor(f"\n[{dados['nome']} · {dados.get('modelo') or ''}]", NEGRITO), flush=True)
        elif tipo == "texto":
            print(dados["delta"], end="", flush=True)
        elif tipo == "passagem":
            estado["agente"] = dados["agente"]
            print(_cor(f"\n\n→ {dados['deNome']} passou a conversa para {dados['nome']}", NEGRITO), flush=True)
        elif tipo == "ferramenta":
            argumentos = ", ".join(f"{k}={v}" for k, v in (dados.get("argumentos") or {}).items() if k != "conteudo")
            print(_cor(f"\n· {dados['nome']}({argumentos[:120]})", CINZA), flush=True)
        elif tipo == "consulta":
            print(_cor(f"\n· consultando {dados['nome']}…", CINZA), flush=True)
        elif tipo == "arquivo":
            print(_cor(f"\n· arquivo: {dados['nome']} ({dados['url']})", CINZA), flush=True)
        elif tipo == "reinicio":
            print(_cor("\n· (resposta reiniciada em outro modelo)", CINZA), flush=True)
        elif tipo in ("aviso", "erro"):
            print(_cor(f"\n{tipo}: {dados['mensagem']}", CINZA), file=sys.stderr, flush=True)
        elif tipo == "membro_fim":
            print(_cor(f"\n── {dados['nome']} ──", NEGRITO))
            print(dados["texto"], flush=True)
        elif tipo == "recusa":
            print(_cor(f"\nO modelo recusou o pedido. {dados.get('detalhe') or ''}", CINZA), flush=True)

    return emitir


def cmd_diagnostico(o: Orquestrador, args) -> int:
    config = o.config
    print(f"Founders OS Agentes {__version__}")
    print(f"configuração: {config.arquivo or '(padrão)'}")
    print(f"skills: {len(o.biblioteca)} de {len(config.fontes_skills)} fonte(s)")
    for fonte in config.fontes_skills:
        print(f"  - {fonte.caminho}")
    especialistas = o.registro.especialistas()
    indisponiveis = [a for a in o.registro.listar() if not a.disponivel]
    print(f"agentes: {len(especialistas)} disponíveis + Recepção; {len(indisponiveis)} indisponíveis")
    for a in indisponiveis:
        print(f"  - {a.id}: {a.motivo_indisponivel}")
    print(f"times: {', '.join(t.id for t in o.registro.times) or '(nenhum)'}")
    print(f"modelo padrão: {config.modelo_padrao}; reserva: {', '.join(config.modelos_reserva) or '(nenhuma)'}")
    print("provedores:")
    for p in o.provedores.situacao():
        detalhe = []
        if "sdkInstalado" in p:
            detalhe.append("SDK ok" if p["sdkInstalado"] else "SDK ausente (pip install anthropic)")
        if p.get("chaveEnv"):
            detalhe.append(f"{p['chaveEnv']} {'definida' if p.get('chaveDefinida') else 'não definida'}")
        print(f"  - {p['nome']} ({p['tipo']}): {'pronto' if p['pronto'] else 'incompleto'}{' — ' + ', '.join(detalhe) if detalhe else ''}")
    print(f"scripts das skills: {'ligados' if config.runtime.permitir_scripts else 'desligados'}")
    print(f"banco: {config.runtime.banco}")
    for aviso in o.avisos:
        print(f"aviso: {aviso}")
    return 0 if len(o.biblioteca) else 1


def cmd_agentes(o: Orquestrador, args) -> int:
    agentes = o.registro.listar()
    if args.json:
        print(json.dumps([a.publico(o.modelo_efetivo(a)) for a in agentes], ensure_ascii=False, indent=2))
        return 0
    areas = list(o.biblioteca.areas) + sorted({a.area or "Outros" for a in agentes} - set(o.biblioteca.areas))
    for area in [None, *areas]:
        itens = [a for a in agentes if a.tipo == "interno"] if area is None else [a for a in agentes if a.tipo != "interno" and (a.area or "Outros") == area]
        if not itens:
            continue
        print(_cor(f"\n{area or 'Entrada'}", NEGRITO))
        for a in itens:
            marca = "" if a.disponivel else _cor(f"  (indisponível: {a.motivo_indisponivel})", CINZA)
            print(f"  {a.id:<42} {a.nome}{marca}")
    return 0


def cmd_perguntar(o: Orquestrador, args) -> int:
    resultado = o.conversar(" ".join(args.mensagem), sessao_id=args.sessao, agente=args.agente, modelo=args.modelo, emitir=_emissor_terminal())
    print(_cor(f"\n\nsessão: {resultado.sessao_id}  ·  tokens: {resultado.uso.entrada} entrada / {resultado.uso.saida} saída", CINZA))
    return 1 if resultado.erro else 0


def cmd_conversar(o: Orquestrador, args) -> int:
    sessao_id = args.sessao
    agente = args.agente or RECEPCAO
    print(_cor("Conversa com os agentes do Founders OS. Ctrl+D ou /sair para sair; /agente <id> troca de agente.", CINZA))
    while True:
        try:
            linha = input(_cor("\nvocê › ", NEGRITO)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not linha:
            continue
        if linha in ("/sair", "/exit"):
            return 0
        if linha.startswith("/agente "):
            agente = linha.split(maxsplit=1)[1].strip()
            o.registro.obter_disponivel(agente)
            print(_cor(f"agora falando com {o.registro.obter(agente).nome}", CINZA))
            continue
        resultado = o.conversar(linha, sessao_id=sessao_id, agente=agente, modelo=args.modelo, emitir=_emissor_terminal())
        sessao_id = resultado.sessao_id
        agente = None  # depois da primeira mensagem, segue com o agente atual da sessão (inclusive após passagens)


def cmd_conselho(o: Orquestrador, args) -> int:
    from .conselho import realizar_conselho

    agentes = [a.strip() for a in (args.agentes or "").split(",") if a.strip()] or None
    resultado = realizar_conselho(o, " ".join(args.pergunta), agentes=agentes, time=args.time, modelo=args.modelo, emitir=_emissor_terminal())
    print(_cor(f"\n\nsessão: {resultado.sessao_id}", CINZA))
    return 1 if resultado.erro else 0


def cmd_sugerir(o: Orquestrador, args) -> int:
    from .roteador import RoteadorLexico

    for agente, pontos in RoteadorLexico(o.registro).sugerir(" ".join(args.mensagem), args.limite):
        print(f"{pontos:7.2f}  {agente.id:<42} {agente.nome}")
    return 0


def cmd_servir(o: Orquestrador, args) -> int:
    from .servidor import servir

    servir(o, host=args.host, porta=args.porta, sem_auth=args.sem_auth)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="founders-agentes", description="Agentes multi-modelo sobre as Skills do Founders OS.")
    parser.add_argument("--config", help="arquivo de configuração TOML (padrão: agentes/config.toml)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("diagnostico", help="confere skills, agentes e provedores").set_defaults(func=cmd_diagnostico)
    p = sub.add_parser("agentes", help="lista os agentes")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_agentes)

    p = sub.add_parser("perguntar", help="manda uma mensagem e mostra a resposta")
    p.add_argument("mensagem", nargs="+")
    p.add_argument("--agente", help="id do agente (padrão: Recepção, que escolhe o especialista)")
    p.add_argument("--modelo", help="força um modelo, ex.: openai:gpt-5.1")
    p.add_argument("--sessao", help="continua uma sessão existente")
    p.set_defaults(func=cmd_perguntar)

    p = sub.add_parser("conversar", help="conversa interativa no terminal")
    p.add_argument("agente", nargs="?")
    p.add_argument("--modelo")
    p.add_argument("--sessao")
    p.set_defaults(func=cmd_conversar)

    p = sub.add_parser("conselho", help="leva uma pergunta a vários agentes e junta as respostas")
    p.add_argument("pergunta", nargs="+")
    p.add_argument("--agentes", help="ids separados por vírgula")
    p.add_argument("--time", help="id de um time da configuração")
    p.add_argument("--modelo")
    p.set_defaults(func=cmd_conselho)

    p = sub.add_parser("sugerir", help="sugere agentes para uma mensagem (sem chamar modelo)")
    p.add_argument("mensagem", nargs="+")
    p.add_argument("--limite", type=int, default=5)
    p.set_defaults(func=cmd_sugerir)

    p = sub.add_parser("servir", help="sobe a API e a interface web")
    p.add_argument("--host")
    p.add_argument("--porta", type=int)
    p.add_argument("--sem-auth", action="store_true", help="permite expor sem chave de API (só em rede confiável)")
    p.set_defaults(func=cmd_servir)

    args = parser.parse_args(argv)
    try:
        orquestrador = Orquestrador(carregar_config(args.config))
    except ErroConfig as exc:
        print(f"erro de configuração: {exc}", file=sys.stderr)
        return 2
    try:
        return args.func(orquestrador, args)
    except Exception as exc:  # noqa: BLE001 - a linha de comando mostra o erro sem traceback
        print(f"erro: {exc}", file=sys.stderr)
        return 1
