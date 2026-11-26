"""Provedor Anthropic (Claude), pelo SDK oficial `anthropic`.

- streaming com o SDK; o texto vai para a tela enquanto é gerado;
- cache de prompt no bloco estável do sistema (as instruções da skill) e no fim da conversa;
- pensamento adaptativo e `effort` nos modelos que aceitam;
- fallback no servidor (beta) nos modelos que recusam por segurança;
- os blocos de raciocínio voltam intactos enquanto o sistema e as ferramentas não mudam.
  Quando mudam (passagem de agente, perfil atualizado), eles saem do histórico,
  porque a API rejeita bloco de raciocínio produzido com outro prefixo.
"""
from __future__ import annotations

import hashlib
import json
import re
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

MAX_TOKENS_PADRAO = 64_000
BETA_FALLBACK = "server-side-fallback-2026-07-01"
MODELOS_COM_FALLBACK = {
    "claude-fable-5-2", "claude-fable-5-1", "claude-mythos-5-2", "claude-mythos-5-1",
    "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
}
_ADAPTATIVO = re.compile(r"^claude-(fable|mythos)-|^claude-(opus|sonnet|haiku)-(5|4-[6-9])")
_RACIOCINIO = {"thinking", "redacted_thinking"}
_PARADAS = {
    "end_turn": "fim",
    "stop_sequence": "fim",
    "tool_use": "ferramenta",
    "max_tokens": "limite",
    "model_context_window_exceeded": "limite",
    "refusal": "recusa",
    "pause_turn": "pausa",
}
_ID_INVALIDO = re.compile(r"[^a-zA-Z0-9_-]")


class ProvedorClaude:
    def __init__(
        self,
        nome: str = "anthropic",
        *,
        chave: str | None = None,
        base_url: str | None = None,
        cliente=None,
        fallbacks: str | list | None = "default",
        max_tokens: int = MAX_TOKENS_PADRAO,
        cache_ttl: str | None = None,
    ) -> None:
        self.nome = nome
        self.chave = chave
        self.base_url = base_url
        self.fallbacks = fallbacks
        self.max_tokens = max_tokens
        self.cache_ttl = cache_ttl
        self._cli = cliente

    def _cliente(self):
        if self._cli is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ErroProvedor("o pacote 'anthropic' não está instalado (pip install anthropic)", provedor=self.nome) from exc
            kwargs = {}
            if self.chave:
                kwargs["api_key"] = self.chave
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._cli = anthropic.Anthropic(**kwargs)
        return self._cli

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
        assinatura = assinatura_prefixo(sistema, ferramentas)
        params: dict = {
            "model": modelo,
            "max_tokens": opcoes.max_tokens or self.max_tokens,
            "system": [self._bloco_sistema(b) for b in sistema],
            "messages": converter_mensagens(mensagens, assinatura, self.nome),
            "cache_control": {"type": "ephemeral"},
        }
        if ferramentas:
            params["tools"] = [
                {"name": f.nome, "description": f.descricao, "input_schema": f.parametros, "eager_input_streaming": True}
                for f in sorted(ferramentas, key=lambda f: f.nome)
            ]
        if _ADAPTATIVO.match(modelo):
            params["thinking"] = {"type": "adaptive"}
            if opcoes.esforco:
                params["output_config"] = {"effort": opcoes.esforco}
        cliente = self._cliente()
        try:
            if self.fallbacks and modelo in MODELOS_COM_FALLBACK:
                fluxo = cliente.beta.messages.stream(betas=[BETA_FALLBACK], fallbacks=self.fallbacks, **params)
            else:
                fluxo = cliente.messages.stream(**params)
            with fluxo as stream:
                for evento in stream:
                    if getattr(evento, "type", None) == "content_block_delta":
                        delta = evento.delta
                        if getattr(delta, "type", None) == "text_delta" and delta.text:
                            ao_texto(delta.text)
                final = stream.get_final_message()
        except ErroProvedor:
            raise
        except Exception as exc:  # noqa: BLE001 - convertido para ErroProvedor abaixo
            raise _converter_erro(exc, self.nome) from exc
        return self._resposta(final, modelo, assinatura)

    def _bloco_sistema(self, bloco: BlocoSistema) -> dict:
        saida = {"type": "text", "text": bloco.texto}
        if bloco.cache:
            saida["cache_control"] = {"type": "ephemeral", **({"ttl": self.cache_ttl} if self.cache_ttl else {})}
        return saida

    def _resposta(self, final, modelo: str, assinatura: str) -> RespostaModelo:
        blocos = [_bloco_para_dict(b) for b in (final.content or [])]
        texto = "".join(b.get("text", "") for b in blocos if b.get("type") == "text")
        chamadas: list[ChamadaFerramenta] = []
        for bloco in blocos:
            if bloco.get("type") == "tool_use":
                argumentos = bloco.get("input")
                chamadas.append(ChamadaFerramenta(
                    id=bloco["id"],
                    nome=bloco["name"],
                    argumentos=argumentos if isinstance(argumentos, dict) else None,
                    erro=None if isinstance(argumentos, dict) else "os argumentos não vieram como objeto JSON",
                ))
        motivo = _PARADAS.get(getattr(final, "stop_reason", None) or "", "fim")
        detalhe = None
        if motivo == "recusa":
            detalhes = getattr(final, "stop_details", None)
            detalhe = getattr(detalhes, "explanation", None) or getattr(detalhes, "category", None)
        uso_bruto = getattr(final, "usage", None)
        uso = Uso(
            entrada=getattr(uso_bruto, "input_tokens", 0) or 0,
            saida=getattr(uso_bruto, "output_tokens", 0) or 0,
            cache_leitura=getattr(uso_bruto, "cache_read_input_tokens", 0) or 0,
            cache_escrita=getattr(uso_bruto, "cache_creation_input_tokens", 0) or 0,
        )
        return RespostaModelo(
            texto=texto,
            chamadas=chamadas,
            motivo_parada=motivo,
            uso=uso,
            raw={"provedor": self.nome, "content": blocos, "assinatura": assinatura},
            modelo=getattr(final, "model", None) or modelo,
            detalhe=detalhe,
        )


def assinatura_prefixo(sistema: list[BlocoSistema], ferramentas: list[EspecFerramenta]) -> str:
    """Identifica o sistema + ferramentas de uma chamada (o que os blocos de raciocínio ficam presos)."""
    dados = {
        "sistema": [b.texto for b in sistema],
        "ferramentas": sorted(
            (f.nome, f.descricao, json.dumps(f.parametros, sort_keys=True, ensure_ascii=False)) for f in ferramentas
        ),
    }
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False).encode()).hexdigest()[:20]


def converter_mensagens(mensagens: list[dict], assinatura: str, provedor: str) -> list[dict]:
    """Converte o histórico neutro para o formato da Messages API."""
    saida: list[dict] = []

    def anexar(papel: str, blocos: list[dict]) -> None:
        if saida and saida[-1]["role"] == papel:
            saida[-1]["content"].extend(blocos)
        else:
            saida.append({"role": papel, "content": list(blocos)})

    for msg in mensagens:
        papel = msg.get("role")
        if papel == "user":
            anexar("user", [{"type": "text", "text": msg.get("content") or "(mensagem vazia)"}])
        elif papel == "assistant":
            raw = msg.get("raw") or {}
            if raw.get("provedor") == provedor and isinstance(raw.get("content"), list):
                blocos = [dict(b) for b in raw["content"]]
                if raw.get("assinatura") != assinatura:
                    blocos = [b for b in blocos if b.get("type") not in _RACIOCINIO]
            else:
                blocos = []
                if msg.get("content"):
                    blocos.append({"type": "text", "text": msg["content"]})
                for chamada in msg.get("tool_calls") or []:
                    blocos.append({
                        "type": "tool_use",
                        "id": _ID_INVALIDO.sub("_", chamada["id"]),
                        "name": chamada["name"],
                        "input": chamada.get("arguments") or {},
                    })
            anexar("assistant", blocos or [{"type": "text", "text": "(sem resposta)"}])
        elif papel == "tool":
            bloco = {
                "type": "tool_result",
                "tool_use_id": _ID_INVALIDO.sub("_", msg["tool_call_id"]),
                "content": msg.get("content") or "(vazio)",
            }
            if msg.get("is_error"):
                bloco["is_error"] = True
            anexar("user", [bloco])
    for msg in saida:
        if msg["role"] == "user":
            msg["content"].sort(key=lambda b: 0 if b.get("type") == "tool_result" else 1)
    return saida


def _bloco_para_dict(bloco) -> dict:
    if isinstance(bloco, dict):
        dados = bloco
    elif hasattr(bloco, "to_dict"):
        dados = bloco.to_dict()
    elif hasattr(bloco, "model_dump"):
        dados = bloco.model_dump(by_alias=True)
    else:
        dados = dict(vars(bloco))
    return _sem_nulos(dados)


def _sem_nulos(valor):
    if isinstance(valor, dict):
        return {k: _sem_nulos(v) for k, v in valor.items() if v is not None}
    if isinstance(valor, list):
        return [_sem_nulos(v) for v in valor]
    return valor


def _converter_erro(exc: Exception, provedor: str) -> ErroProvedor:
    try:
        import anthropic
    except ImportError:
        anthropic = None
    if anthropic is not None:
        if isinstance(exc, anthropic.APIStatusError):
            status = exc.status_code
            return ErroProvedor(
                f"HTTP {status}: {getattr(exc, 'message', exc)}",
                status=status,
                repetivel=status in (408, 409, 429) or status >= 500,
                provedor=provedor,
            )
        if isinstance(exc, anthropic.APIConnectionError):
            return ErroProvedor(f"falha de conexão: {exc}", repetivel=True, provedor=provedor)
    if isinstance(exc, ValueError):
        # streaming antecipado de ferramenta: JSON que o SDK não conseguiu ler; vale refazer o turno
        return ErroProvedor(f"entrada de ferramenta ilegível: {exc}", repetivel=True, provedor=provedor)
    return ErroProvedor(f"{type(exc).__name__}: {exc}", provedor=provedor)
