"""Tipos comuns a todos os provedores de modelo.

A conversa é guardada num formato neutro (lista de dicts) para poder trocar de
modelo ou de provedor no meio dela:

    {"role": "user", "content": "texto"}
    {"role": "assistant", "content": "texto", "tool_calls": [{"id", "name", "arguments"}],
     "raw": {"provedor": "anthropic", "content": [...], "assinatura": "..."}}
    {"role": "tool", "tool_call_id": "...", "name": "...", "content": "texto", "is_error": False}

Cada provedor converte desse formato para o da sua API. "raw" guarda a mensagem
original do provedor, para reenviar exatamente igual quando o mesmo provedor
continua a conversa (o Claude exige isso para os blocos de raciocínio).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class BlocoSistema:
    texto: str
    cache: bool = False


@dataclass
class EspecFerramenta:
    nome: str
    descricao: str
    parametros: dict


@dataclass
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict | None
    erro: str | None = None  # argumentos inválidos (JSON quebrado, cortado etc.)


@dataclass
class OpcoesChamada:
    max_tokens: int | None = None
    esforco: str | None = None
    agente_id: str | None = None
    agente_nome: str | None = None


@dataclass
class Uso:
    entrada: int = 0
    saida: int = 0
    cache_leitura: int = 0
    cache_escrita: int = 0

    def somar(self, outro: "Uso") -> None:
        self.entrada += outro.entrada
        self.saida += outro.saida
        self.cache_leitura += outro.cache_leitura
        self.cache_escrita += outro.cache_escrita

    def como_dict(self) -> dict:
        return {"entrada": self.entrada, "saida": self.saida, "cacheLeitura": self.cache_leitura, "cacheEscrita": self.cache_escrita}


@dataclass
class RespostaModelo:
    texto: str
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    motivo_parada: str = "fim"  # fim | ferramenta | limite | recusa | pausa
    uso: Uso = field(default_factory=Uso)
    raw: dict | None = None
    modelo: str = ""
    detalhe: str | None = None


class ErroProvedor(Exception):
    def __init__(self, mensagem: str, *, status: int | None = None, repetivel: bool = False, provedor: str | None = None):
        super().__init__(mensagem)
        self.status = status
        self.repetivel = repetivel
        self.provedor = provedor


class Provedor(Protocol):
    nome: str

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
        """Chama o modelo em streaming, repassa cada pedaço de texto para ao_texto e devolve a resposta inteira."""
        ...
