"""API HTTP, só com a biblioteca padrão.

- API própria (/v1/agentes, /v1/conversa, /v1/conselho...) com eventos ao vivo (SSE);
- endpoint compatível com a OpenAI (/v1/models, /v1/chat/completions): cada agente
  aparece como um "modelo", então Open WebUI, LibreChat, n8n, Typebot e qualquer
  cliente da OpenAI conversam com os agentes sem código novo;
- a interface web de conversa em /.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import re
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .agentes import RECEPCAO, ErroAgente
from .armazenamento import Sessao
from .conselho import realizar_conselho
from .conselho import MAX_MEMBROS, MIN_MEMBROS
from .orquestrador import Orquestrador, resumir_argumentos
from .provedores import ErroProvedor
from .roteador import RoteadorLexico
from .skills import ErroSkill

PASTA_WEB = Path(__file__).resolve().parent.parent / "web"
PASTA_SITE = Path(__file__).resolve().parent.parent.parent / "site"
MAX_CORPO = 1_000_000
_AUTO = ("auto", "automatico", "founders-os")


class ErroHTTP(Exception):
    def __init__(self, status: int, mensagem: str, codigo: str | None = None) -> None:
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem
        self.codigo = codigo


class Aplicacao:
    def __init__(self, orquestrador: Orquestrador, pasta_web: Path = PASTA_WEB, silencioso: bool = False) -> None:
        self.o = orquestrador
        self.pasta_web = pasta_web
        self.silencioso = silencioso
        self.roteador = RoteadorLexico(orquestrador.registro)
        self.rotas = [
            ("GET", r"/saude", self.saude, False),
            ("GET", r"/v1/agentes", self.listar_agentes, True),
            ("GET", r"/v1/agentes/(?P<agente>[^/]+)", self.obter_agente, True),
            ("GET", r"/v1/skills", self.listar_skills, True),
            ("GET", r"/v1/times", self.listar_times, True),
            ("GET", r"/v1/provedores", self.listar_provedores, True),
            ("GET", r"/v1/sugerir", self.sugerir, True),
            ("GET", r"/v1/sessoes", self.listar_sessoes, True),
            ("POST", r"/v1/sessoes", self.criar_sessao, True),
            ("GET", r"/v1/sessoes/(?P<sessao>[A-Za-z0-9_-]+)", self.obter_sessao, True),
            ("GET", r"/v1/sessoes/(?P<sessao>[A-Za-z0-9_-]+)/arquivos/(?P<nome>[^/]+)", self.baixar_arquivo, True),
            ("POST", r"/v1/conversa", self.conversa, True),
            ("POST", r"/v1/conselho", self.conselho, True),
            ("GET", r"/v1/perfil", self.obter_perfil, True),
            ("PUT", r"/v1/perfil", self.salvar_perfil, True),
            ("GET", r"/v1/models", self.openai_modelos, True),
            ("POST", r"/v1/chat/completions", self.openai_chat, True),
            ("GET", r"/", self.estatico, False),
            ("GET", r"/web/(?P<arquivo>[A-Za-z0-9_.-]+)", self.estatico, False),
            ("GET", r"/site/(?P<arquivo>icones\.js|img/[A-Za-z0-9_.-]+\.(?:svg|webp|png))", self.marca, False),
        ]

    # -- infraestrutura ---------------------------------------------------
    def classe_handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"FoundersOSAgentes/{__version__}"

            def do_GET(self):
                app.despachar(self, "GET")

            def do_POST(self):
                app.despachar(self, "POST")

            def do_PUT(self):
                app.despachar(self, "PUT")

            def do_OPTIONS(self):
                self.send_response(204)
                app.cabecalhos_cors(self)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, formato, *args):
                if app.silencioso:
                    return
                sys.stderr.write("%s %s\n" % (self.log_date_time_string(), formato % args))

            def log_request(self, code="-", size="-"):
                caminho = urlparse(self.path).path
                self.log_message('"%s %s" %s', self.command, caminho, code)

        return Handler

    def despachar(self, h: BaseHTTPRequestHandler, metodo: str) -> None:
        url = urlparse(h.path)
        caminho = url.path.rstrip("/") or "/"
        try:
            for verbo, padrao, funcao, protegida in self.rotas:
                casamento = re.fullmatch(padrao, caminho)
                if casamento is None:
                    continue
                if verbo != metodo:
                    continue
                dono = self.dono(h) if protegida else "local"
                consulta = {k: v[-1] for k, v in parse_qs(url.query).items()}
                funcao(h, dono=dono, consulta=consulta, **{k: unquote(v) for k, v in casamento.groupdict().items()})
                return
            if any(re.fullmatch(p, caminho) for _, p, _, _ in self.rotas):
                raise ErroHTTP(405, "método não permitido")
            raise ErroHTTP(404, "rota não encontrada")
        except ErroHTTP as exc:
            self.json(h, exc.status, {"error": {"message": exc.mensagem, "type": "invalid_request_error", "code": exc.codigo}})
        except (ErroAgente, ErroSkill) as exc:
            self.json(h, 404, {"error": {"message": str(exc), "type": "invalid_request_error", "code": "not_found"}})
        except (ValueError, ErroProvedor) as exc:
            self.json(h, 400, {"error": {"message": str(exc), "type": "invalid_request_error", "code": None}})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            try:
                self.json(h, 500, {"error": {"message": "erro interno", "type": "server_error", "code": None}})
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def dono(self, h: BaseHTTPRequestHandler) -> str:
        chaves = self.o.config.servidor.chaves_api
        if not chaves:
            return "local"
        autorizacao = h.headers.get("Authorization", "")
        token = autorizacao[7:].strip() if autorizacao.lower().startswith("bearer ") else h.headers.get("X-API-Key", "").strip()
        for chave, dono in chaves.items():
            if token and hmac.compare_digest(token.encode(), chave.encode()):
                return dono
        raise ErroHTTP(401, "chave de API ausente ou inválida", "invalid_api_key")

    def cabecalhos_cors(self, h: BaseHTTPRequestHandler) -> None:
        origem = self.o.config.servidor.cors
        if origem:
            h.send_header("Access-Control-Allow-Origin", origem)
            h.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-API-Key, X-Session-Id")
            h.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")

    def json(self, h: BaseHTTPRequestHandler, status: int, dados) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Length", str(len(corpo)))
        self.cabecalhos_cors(h)
        h.end_headers()
        h.wfile.write(corpo)

    def corpo(self, h: BaseHTTPRequestHandler) -> dict:
        tamanho = int(h.headers.get("Content-Length") or 0)
        if tamanho > MAX_CORPO:
            raise ErroHTTP(413, "corpo grande demais")
        bruto = h.rfile.read(tamanho) if tamanho else b"{}"
        try:
            dados = json.loads(bruto or b"{}")
        except ValueError:
            raise ErroHTTP(400, "JSON inválido") from None
        if not isinstance(dados, dict):
            raise ErroHTTP(400, "o corpo precisa ser um objeto JSON")
        return dados

    def abrir_sse(self, h: BaseHTTPRequestHandler):
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream; charset=utf-8")
        h.send_header("Cache-Control", "no-cache")
        h.send_header("X-Accel-Buffering", "no")
        self.cabecalhos_cors(h)
        h.end_headers()
        h.close_connection = True
        trava = threading.Lock()

        def escrever(bloco: str) -> None:
            with trava:
                try:
                    h.wfile.write(bloco.encode("utf-8"))
                    h.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        return escrever

    def executar_com_eventos(self, h: BaseHTTPRequestHandler, stream: bool, executar) -> None:
        if stream:
            escrever = self.abrir_sse(h)

            def emitir(tipo: str, dados: dict) -> None:
                escrever(f"event: {tipo}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n")

            try:
                executar(emitir)
            except (ErroAgente, ErroSkill, ValueError) as exc:
                emitir("erro", {"mensagem": str(exc)})
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                emitir("erro", {"mensagem": "erro interno"})
            return
        eventos: list[dict] = []
        resultado = executar(lambda tipo, dados: eventos.append({"tipo": tipo, **dados}) if tipo not in ("texto", "membro_texto") else None)
        self.json(h, 200, {
            "sessaoId": resultado.sessao_id,
            "agente": resultado.agente,
            "texto": resultado.texto,
            "uso": resultado.uso.como_dict(),
            "erro": resultado.erro,
            "eventos": eventos,
        })

    # -- rotas: catálogo --------------------------------------------------
    def saude(self, h, **_):
        self.json(h, 200, {"ok": True, "versao": __version__, "skills": len(self.o.biblioteca), "agentes": len(self.o.registro.especialistas())})

    def listar_agentes(self, h, **_):
        agentes = [a.publico(self.o.modelo_efetivo(a)) for a in self.o.registro.listar()]
        self.json(h, 200, {"areas": self.o.biblioteca.areas, "agentes": agentes})

    def obter_agente(self, h, agente: str, **_):
        a = self.o.registro.obter(agente)
        dados = a.publico(self.o.modelo_efetivo(a))
        dados["cadeiaDeModelos"] = self.o.cadeia_de_modelos(a, None)
        dados["ferramentas"] = [f.nome for f in self.o.ferramentas.para_agente(a)]
        self.json(h, 200, dados)

    def listar_skills(self, h, **_):
        self.json(h, 200, {"areas": self.o.biblioteca.areas, "skills": [s.resumo_publico() for s in self.o.biblioteca]})

    def listar_times(self, h, **_):
        self.json(h, 200, {"times": [t.publico() for t in self.o.registro.times]})

    def listar_provedores(self, h, **_):
        self.json(h, 200, {
            "modeloPadrao": self.o.config.modelo_padrao,
            "reserva": self.o.config.modelos_reserva,
            "apelidos": self.o.config.apelidos,
            "provedores": self.o.provedores.situacao(),
        })

    def sugerir(self, h, consulta, **_):
        texto = consulta.get("q", "")
        sugestoes = [{"agente": a.id, "nome": a.nome, "area": a.area, "pontos": p} for a, p in self.roteador.sugerir(texto, int(consulta.get("limite", 5)))]
        self.json(h, 200, {"sugestoes": sugestoes})

    # -- rotas: sessões ---------------------------------------------------
    def listar_sessoes(self, h, dono, **_):
        self.json(h, 200, {"sessoes": self.o.armazenamento.listar_sessoes(dono)})

    def criar_sessao(self, h, dono, **_):
        dados = self.corpo(h)
        agente = dados.get("agente")
        if agente and agente not in _AUTO:
            self.o.registro.obter_disponivel(agente)
        sessao = self.o.armazenamento.criar_sessao(dono, agente=None if agente in _AUTO else agente)
        self.json(h, 201, {"id": sessao.id, "agenteAtual": sessao.agente_atual})

    def obter_sessao(self, h, dono, sessao, **_):
        s = self.o.armazenamento.obter_sessao(sessao, dono)
        if s is None:
            raise ErroHTTP(404, "sessão não encontrada")
        pasta = self.o.armazenamento.pasta_arquivos / s.id
        arquivos = [
            {"nome": p.name, "tamanho": p.stat().st_size, "url": f"/v1/sessoes/{s.id}/arquivos/{p.name}"}
            for p in sorted(pasta.iterdir()) if p.is_file()
        ] if pasta.is_dir() else []
        self.json(h, 200, {
            "id": s.id,
            "titulo": s.titulo,
            "agenteAtual": s.agente_atual,
            "mensagens": _mensagens_para_tela(s.mensagens),
            "consumo": self.o.armazenamento.consumo(s.id),
            "arquivos": arquivos,
        })

    def baixar_arquivo(self, h, dono, sessao, nome, **_):
        if self.o.armazenamento.obter_sessao(sessao, dono) is None:
            raise ErroHTTP(404, "sessão não encontrada")
        caminho = self.o.armazenamento.caminho_arquivo(sessao, nome)
        if caminho is None:
            raise ErroHTTP(404, "arquivo não encontrado")
        dados = caminho.read_bytes()
        h.send_response(200)
        h.send_header("Content-Type", mimetypes.guess_type(nome)[0] or "application/octet-stream")
        h.send_header("Content-Length", str(len(dados)))
        h.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + _cod_url(nome))
        self.cabecalhos_cors(h)
        h.end_headers()
        h.wfile.write(dados)

    def conversa(self, h, dono, **_):
        dados = self.corpo(h)
        mensagem = str(dados.get("mensagem") or "").strip()
        if not mensagem:
            raise ErroHTTP(400, "mande a mensagem")
        sessao_id = dados.get("sessaoId")
        agente = dados.get("agente")
        if sessao_id and self.o.armazenamento.obter_sessao(sessao_id, dono) is None:
            raise ErroHTTP(404, "sessão não encontrada")
        if agente and agente not in _AUTO:
            self.o.registro.obter_disponivel(agente)
        modelo = dados.get("modelo") or None
        if modelo:
            self.o.provedores.separar(modelo)
        self.executar_com_eventos(h, dados.get("stream", True), lambda emitir: self.o.conversar(
            mensagem, sessao_id=sessao_id, agente=agente, modelo=modelo, dono=dono, emitir=emitir,
        ))

    def conselho(self, h, dono, **_):
        dados = self.corpo(h)
        pergunta = str(dados.get("pergunta") or "").strip()
        if not pergunta:
            raise ErroHTTP(400, "mande a pergunta")
        agentes = dados.get("agentes")
        time_id = dados.get("time")
        if time_id:
            self.o.registro.obter_time(time_id)
        elif not isinstance(agentes, list):
            raise ErroHTTP(400, "mande 'agentes' (lista de ids) ou 'time'")
        elif not MIN_MEMBROS <= len(set(agentes)) <= MAX_MEMBROS:
            raise ErroHTTP(400, f"o conselho precisa de {MIN_MEMBROS} a {MAX_MEMBROS} agentes")
        else:
            for a in agentes:
                self.o.registro.obter_disponivel(a)
        self.executar_com_eventos(h, dados.get("stream", True), lambda emitir: realizar_conselho(
            self.o, pergunta, agentes=agentes, time=time_id, sessao_id=dados.get("sessaoId"), dono=dono,
            modelo=dados.get("modelo") or None, emitir=emitir,
        ))

    def obter_perfil(self, h, dono, **_):
        self.json(h, 200, {"perfil": self.o.armazenamento.obter_perfil(dono)})

    def salvar_perfil(self, h, dono, **_):
        dados = self.corpo(h)
        perfil = dados.get("perfil")
        if not isinstance(perfil, dict):
            raise ErroHTTP(400, "mande {\"perfil\": {...}}")
        self.json(h, 200, {"perfil": self.o.armazenamento.atualizar_perfil(dono, perfil, substituir=bool(dados.get("substituir")))})

    # -- rotas: compatível com a OpenAI ----------------------------------
    def openai_modelos(self, h, **_):
        criado = int(time.time())
        modelos = [{"id": "auto", "object": "model", "created": criado, "owned_by": "founders-os"}]
        modelos += [{"id": a.id, "object": "model", "created": criado, "owned_by": "founders-os", "name": a.nome} for a in self.o.registro.especialistas()]
        self.json(h, 200, {"object": "list", "data": modelos})

    def openai_chat(self, h, dono, **_):
        dados = self.corpo(h)
        modelo = str(dados.get("model") or "auto")
        agente_id = RECEPCAO if modelo in _AUTO else modelo
        if agente_id not in self.o.registro or not self.o.registro.obter(agente_id).disponivel:
            raise ErroHTTP(404, f"o modelo '{modelo}' não existe: use um id de GET /v1/models", "model_not_found")
        mensagens = [(m.get("role"), _texto_openai(m.get("content"))) for m in dados.get("messages") or [] if isinstance(m, dict)]
        indice = max((i for i, (papel, texto) in enumerate(mensagens) if papel == "user" and texto.strip()), default=None)
        if indice is None:
            raise ErroHTTP(400, "nenhuma mensagem do usuário em 'messages'")
        pergunta = mensagens[indice][1]
        sessao_id = h.headers.get("X-Session-Id") or (dados.get("metadata") or {}).get("session_id")

        if sessao_id:
            existente = self.o.armazenamento.obter_sessao(sessao_id, dono)
            if existente is None and self.o.armazenamento.existe_sessao(sessao_id):
                raise ErroHTTP(404, "sessão não encontrada")
            agente_pedido = agente_id if (existente is None and modelo not in _AUTO) else None

            def executar(emitir):
                return self.o.conversar(pergunta, sessao_id=sessao_id, agente=agente_pedido, dono=dono, emitir=emitir, criar_com_id=True)
        else:
            sessao = Sessao.efemera(dono, agente_id)
            for papel, texto in mensagens[:indice]:
                if papel in ("user", "assistant") and texto.strip():
                    sessao.mensagens.append({"role": papel, "content": texto})
            while sessao.mensagens and sessao.mensagens[0]["role"] != "user":
                sessao.mensagens.pop(0)

            def executar(emitir):
                return self.o.conversar_na_sessao(sessao, pergunta, agente=agente_id, emitir=emitir)

        ident = "chatcmpl-" + uuid.uuid4().hex[:24]
        criado = int(time.time())
        mostrar = self.o.config.servidor.eventos_no_openai
        uso = {}

        def traduzir(tipo: str, dados_evento: dict) -> str | None:
            if tipo == "texto":
                return dados_evento["delta"]
            if tipo == "fim":
                uso.update(dados_evento.get("uso") or {})
            if not mostrar:
                return None
            if tipo == "passagem":
                return f"\n\n*{dados_evento['nome']} assumiu a conversa.*\n\n"
            if tipo == "consulta":
                return f"\n\n*Consultando {dados_evento['nome']}…*\n\n"
            if tipo == "reinicio":
                return "\n\n*(resposta reiniciada)*\n\n"
            if tipo == "erro":
                return f"\n\n**Erro:** {dados_evento['mensagem']}\n\n"
            return None

        if dados.get("stream"):
            escrever = self.abrir_sse(h)

            def pedaco(delta: dict, fim: str | None = None) -> None:
                corpo = {"id": ident, "object": "chat.completion.chunk", "created": criado, "model": modelo,
                         "choices": [{"index": 0, "delta": delta, "finish_reason": fim}]}
                escrever(f"data: {json.dumps(corpo, ensure_ascii=False)}\n\n")

            pedaco({"role": "assistant", "content": ""})

            def emitir(tipo, dados_evento):
                texto = traduzir(tipo, dados_evento)
                if texto:
                    pedaco({"content": texto})

            try:
                executar(emitir)
            except (ErroAgente, ErroSkill, ValueError) as exc:
                pedaco({"content": f"\n\n**Erro:** {exc}"})
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                pedaco({"content": "\n\n**Erro interno.**"})
            pedaco({}, "stop")
            escrever("data: [DONE]\n\n")
            return

        partes: list[str] = []
        executar(lambda tipo, d: partes.append(traduzir(tipo, d) or ""))
        self.json(h, 200, {
            "id": ident,
            "object": "chat.completion",
            "created": criado,
            "model": modelo,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(partes).strip()}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": uso.get("entrada", 0),
                "completion_tokens": uso.get("saida", 0),
                "total_tokens": uso.get("entrada", 0) + uso.get("saida", 0),
            },
        })

    # -- interface web ----------------------------------------------------
    def estatico(self, h, arquivo: str = "index.html", **_):
        self.enviar_arquivo(h, self.pasta_web, arquivo)

    def marca(self, h, arquivo: str, **_):
        """Ícones e logos do site do Founders OS, reaproveitados pela interface de conversa."""
        self.enviar_arquivo(h, PASTA_SITE, arquivo)

    def enviar_arquivo(self, h, pasta: Path, arquivo: str) -> None:
        caminho = (pasta / arquivo).resolve()
        if pasta.resolve() not in caminho.parents or not caminho.is_file():
            raise ErroHTTP(404, "arquivo não encontrado")
        dados = caminho.read_bytes()
        tipo = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "application/json"):
            tipo += "; charset=utf-8"
        h.send_response(200)
        h.send_header("Content-Type", tipo)
        h.send_header("Content-Length", str(len(dados)))
        h.send_header("Cache-Control", "no-cache")
        h.end_headers()
        h.wfile.write(dados)


def _texto_openai(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "\n".join(p.get("text", "") for p in conteudo if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
    return ""


def _mensagens_para_tela(mensagens: list[dict]) -> list[dict]:
    tela: list[dict] = []
    for m in mensagens:
        if m.get("role") == "user":
            tela.append({"papel": "usuario", "texto": m.get("content", ""), "conselho": m.get("conselho")})
        elif m.get("role") == "assistant":
            ferramentas = [{"nome": c["name"], "argumentos": resumir_argumentos(c.get("arguments"))} for c in m.get("tool_calls") or []]
            if not (m.get("content") or "").strip() and not ferramentas:
                continue
            tela.append({"papel": "agente", "agente": m.get("agente"), "modelo": m.get("modelo"), "texto": m.get("content", ""),
                         "ferramentas": ferramentas, "conselho": m.get("conselho") if isinstance(m.get("conselho"), dict) else None})
    return tela


def _cod_url(texto: str) -> str:
    from urllib.parse import quote

    return quote(texto, safe="")


def servir(orquestrador: Orquestrador, host: str | None = None, porta: int | None = None, sem_auth: bool = False) -> None:
    config = orquestrador.config.servidor
    host = host or config.host
    porta = porta or config.porta
    if not config.chaves_api and host not in ("127.0.0.1", "localhost", "::1") and not sem_auth:
        raise SystemExit(
            "Servidor exposto na rede sem chave de API. Defina FOUNDERS_AGENTES_CHAVES=\"chave:dono,...\" "
            "ou rode com --sem-auth (só em rede confiável)."
        )
    app = Aplicacao(orquestrador)
    servidor = ThreadingHTTPServer((host, porta), app.classe_handler())
    servidor.daemon_threads = True
    print(
        f"Founders OS Agentes {__version__} em http://{host}:{porta}  "
        f"({len(orquestrador.registro.especialistas())} agentes, {len(orquestrador.biblioteca)} skills, "
        f"modelo padrão {orquestrador.config.modelo_padrao})",
        flush=True,
    )
    for aviso in orquestrador.avisos:
        print(f"aviso: {aviso}", file=sys.stderr)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
