"""Provedor para qualquer API no formato Chat Completions da OpenAI.

Cobre OpenAI, OpenRouter (que dá acesso a centenas de modelos), Gemini (endpoint
compatível), Groq, DeepSeek, Mistral, xAI, Together, Ollama, LM Studio, vLLM etc.
Usa só a biblioteca padrão (urllib), com streaming SSE.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from .base import (
    BlocoSistema,
    ChamadaFerramenta,
    EspecFerramenta,
    ErroProvedor,
    OpcoesChamada,
    RespostaModelo,
    Uso,
)

_PARADAS = {"stop": "fim", "tool_calls": "ferramenta", "function_call": "ferramenta", "length": "limite", "content_filter": "recusa"}
_ESFORCO_OPENAI = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


class ProvedorOpenAICompat:
    def __init__(
        self,
        nome: str,
        *,
        base_url: str,
        chave: str | None = None,
        cabecalhos: dict[str, str] | None = None,
        timeout: float = 300.0,
        max_tokens: int | None = None,
        enviar_esforco: bool = False,
        uso_no_stream: bool = True,
        max_mensagens: int = 0,
    ) -> None:
        self.nome = nome
        self.base_url = base_url.rstrip("/")
        self.chave = chave
        self.cabecalhos = dict(cabecalhos or {})
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.enviar_esforco = enviar_esforco
        self.uso_no_stream = uso_no_stream
        self.max_mensagens = max_mensagens

    def gerar(
        self,
        *,
        modelo: str,
        sistema: list[BlocoSistema],
        mensagens: list[dict],
        ferramentas: list[EspecFerramenta],
        opcoes: OpcoesChamada,
        ao_texto: Callable[[str], None],
    ) -> RespostaModelo:
        corpo: dict = {
            "model": modelo,
            "messages": [{"role": "system", "content": "\n\n".join(b.texto for b in sistema)}]
            + converter_mensagens(mensagens, self.max_mensagens),
            "stream": True,
        }
        if self.uso_no_stream:
            corpo["stream_options"] = {"include_usage": True}
        if ferramentas:
            corpo["tools"] = [
                {"type": "function", "function": {"name": f.nome, "description": f.descricao, "parameters": f.parametros}}
                for f in sorted(ferramentas, key=lambda f: f.nome)
            ]
        if opcoes.max_tokens or self.max_tokens:
            corpo["max_tokens"] = opcoes.max_tokens or self.max_tokens
        if self.enviar_esforco and opcoes.esforco:
            corpo["reasoning_effort"] = _ESFORCO_OPENAI.get(opcoes.esforco, opcoes.esforco)

        cabecalhos = {"Content-Type": "application/json", "Accept": "text/event-stream", **self.cabecalhos}
        if self.chave:
            cabecalhos["Authorization"] = f"Bearer {self.chave}"
        pedido = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
            headers=cabecalhos,
            method="POST",
        )
        try:
            resposta = urllib.request.urlopen(pedido, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            with exc:
                detalhe = _ler_erro(exc)
            raise ErroProvedor(
                f"HTTP {exc.code}: {detalhe}",
                status=exc.code,
                repetivel=exc.code in (408, 409, 429) or exc.code >= 500,
                provedor=self.nome,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ErroProvedor(f"falha de conexão com {self.base_url}: {exc}", repetivel=True, provedor=self.nome) from exc

        textos: list[str] = []
        chamadas: dict[int, dict] = {}
        ordem: list[int] = []
        motivo = None
        uso = Uso()
        modelo_resposta = modelo
        try:
            with resposta:
                for dado in _eventos_sse(resposta):
                    if dado.strip() == "[DONE]":
                        break
                    try:
                        pedaco = json.loads(dado)
                    except ValueError:
                        continue
                    if pedaco.get("error"):
                        erro = pedaco["error"]
                        mensagem = erro.get("message") if isinstance(erro, dict) else str(erro)
                        raise ErroProvedor(f"erro no stream: {mensagem}", provedor=self.nome)
                    modelo_resposta = pedaco.get("model") or modelo_resposta
                    if pedaco.get("usage"):
                        uso = _uso(pedaco["usage"])
                    for escolha in pedaco.get("choices") or []:
                        delta = escolha.get("delta") or escolha.get("message") or {}
                        conteudo = delta.get("content")
                        if isinstance(conteudo, str) and conteudo:
                            textos.append(conteudo)
                            ao_texto(conteudo)
                        for parcial in delta.get("tool_calls") or []:
                            _acumular_chamada(chamadas, ordem, parcial)
                        if escolha.get("finish_reason"):
                            motivo = escolha["finish_reason"]
        except ErroProvedor:
            raise
        except (OSError, TimeoutError) as exc:
            raise ErroProvedor(f"conexão caiu no meio da resposta: {exc}", repetivel=True, provedor=self.nome) from exc

        lista = [_finalizar_chamada(chamadas[i], n) for n, i in enumerate(ordem)]
        parada = _PARADAS.get(motivo or "stop", "fim")
        if lista and parada == "fim":
            parada = "ferramenta"
        return RespostaModelo(texto="".join(textos), chamadas=lista, motivo_parada=parada, uso=uso, modelo=modelo_resposta)


def converter_mensagens(mensagens: list[dict], max_mensagens: int = 0) -> list[dict]:
    saida: list[dict] = []
    for msg in mensagens:
        papel = msg.get("role")
        if papel == "user":
            saida.append({"role": "user", "content": msg.get("content") or ""})
        elif papel == "assistant":
            item: dict = {"role": "assistant", "content": msg.get("content") or None}
            if msg.get("tool_calls"):
                item["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False)},
                    }
                    for c in msg["tool_calls"]
                ]
            elif item["content"] is None:
                item["content"] = ""
            saida.append(item)
        elif papel == "tool":
            saida.append({"role": "tool", "tool_call_id": msg["tool_call_id"], "content": msg.get("content") or ""})
    if max_mensagens and len(saida) > max_mensagens:
        corte = len(saida) - max_mensagens
        while corte < len(saida) and saida[corte]["role"] != "user":
            corte += 1
        saida = saida[corte:]
    return saida


def _eventos_sse(resposta):
    linhas: list[str] = []
    for bruta in resposta:
        linha = bruta.decode("utf-8", errors="replace").rstrip("\r\n")
        if linha == "":
            if linhas:
                yield "\n".join(linhas)
                linhas = []
            continue
        if linha.startswith(":"):
            continue
        if linha.startswith("data:"):
            valor = linha[5:]
            linhas.append(valor[1:] if valor.startswith(" ") else valor)
    if linhas:
        yield "\n".join(linhas)


def _acumular_chamada(chamadas: dict[int, dict], ordem: list[int], parcial: dict) -> None:
    indice = parcial.get("index")
    if indice is None:
        ident = parcial.get("id")
        conhecido = next((i for i, c in chamadas.items() if ident and c["id"] == ident), None)
        if conhecido is not None:
            indice = conhecido
        elif ident or not ordem:
            indice = (max(chamadas) + 1) if chamadas else 0
        else:
            indice = ordem[-1]
    if indice not in chamadas:
        chamadas[indice] = {"id": None, "nome": "", "args": ""}
        ordem.append(indice)
    slot = chamadas[indice]
    if parcial.get("id"):
        slot["id"] = parcial["id"]
    funcao = parcial.get("function") or {}
    if funcao.get("name") and not slot["nome"]:
        slot["nome"] = funcao["name"]
    argumentos = funcao.get("arguments")
    if isinstance(argumentos, str):
        slot["args"] += argumentos
    elif isinstance(argumentos, dict):
        slot["args"] = json.dumps(argumentos, ensure_ascii=False)


def _finalizar_chamada(slot: dict, posicao: int) -> ChamadaFerramenta:
    ident = slot["id"] or f"chamada_{posicao}"
    texto = slot["args"].strip() or "{}"
    try:
        argumentos = json.loads(texto)
    except ValueError:
        return ChamadaFerramenta(id=ident, nome=slot["nome"], argumentos=None, erro="argumentos em JSON inválido")
    if not isinstance(argumentos, dict):
        return ChamadaFerramenta(id=ident, nome=slot["nome"], argumentos=None, erro="os argumentos não são um objeto JSON")
    return ChamadaFerramenta(id=ident, nome=slot["nome"], argumentos=argumentos)


def _uso(dados: dict) -> Uso:
    detalhes = dados.get("prompt_tokens_details") or {}
    return Uso(
        entrada=int(dados.get("prompt_tokens") or 0),
        saida=int(dados.get("completion_tokens") or 0),
        cache_leitura=int(detalhes.get("cached_tokens") or 0),
    )


def _ler_erro(exc: urllib.error.HTTPError) -> str:
    try:
        corpo = exc.read(4000).decode("utf-8", errors="replace")
    except OSError:
        return exc.reason or "erro"
    try:
        dados = json.loads(corpo)
    except ValueError:
        return corpo[:500] or (exc.reason or "erro")
    erro = dados.get("error") if isinstance(dados, dict) else None
    if isinstance(erro, dict):
        return str(erro.get("message") or erro)[:500]
    return str(erro or dados)[:500]
