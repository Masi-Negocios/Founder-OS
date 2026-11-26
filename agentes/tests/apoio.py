"""Apoio dos testes: configuração temporária e provedores roteirizados (sem rede)."""
from __future__ import annotations

import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from founders_agentes.config import carregar_config  # noqa: E402
from founders_agentes.orquestrador import Orquestrador  # noqa: E402
from founders_agentes.provedores import ChamadaFerramenta, ErroProvedor, RespostaModelo, Uso  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "marketplace"


def texto(conteudo: str, **kwargs) -> RespostaModelo:
    return RespostaModelo(texto=conteudo, uso=Uso(entrada=10, saida=5), **kwargs)


_contador = [0]


def ferramenta(nome_ferramenta: str, /, texto_antes: str = "", **argumentos) -> RespostaModelo:
    _contador[0] += 1
    return RespostaModelo(
        texto=texto_antes,
        chamadas=[ChamadaFerramenta(id=f"t{_contador[0]}", nome=nome_ferramenta, argumentos=argumentos)],
        motivo_parada="ferramenta",
        uso=Uso(entrada=10, saida=5),
    )


class ProvedorRoteiro:
    """Devolve as respostas na ordem; cada item pode ser RespostaModelo, função(chamada) ou exceção."""

    def __init__(self, respostas=(), nome: str = "roteiro", texto_antes_de_falhar: str = "") -> None:
        self.nome = nome
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []
        self.texto_antes_de_falhar = texto_antes_de_falhar
        self._trava = threading.Lock()

    def gerar(self, *, modelo, sistema, mensagens, ferramentas, opcoes, ao_texto):
        with self._trava:
            chamada = {
                "modelo": modelo,
                "sistema": [b.texto for b in sistema],
                "mensagens": copy.deepcopy(mensagens),
                "ferramentas": [f.nome for f in ferramentas],
                "especs": ferramentas,
                "opcoes": opcoes,
            }
            self.chamadas.append(chamada)
            if not self.respostas:
                raise AssertionError(f"roteiro de {self.nome} acabou")
            resposta = self.respostas.pop(0)
        if callable(resposta) and not isinstance(resposta, RespostaModelo):
            resposta = resposta(chamada)
        if isinstance(resposta, Exception):
            if self.texto_antes_de_falhar:
                ao_texto(self.texto_antes_de_falhar)
            raise resposta
        if resposta.texto:
            ao_texto(resposta.texto)
        return resposta


class ProvedorFuncao:
    """Responde com uma função de (chamada) -> RespostaModelo; seguro para chamadas em paralelo."""

    def __init__(self, funcao, nome: str = "funcao") -> None:
        self.nome = nome
        self.funcao = funcao
        self.chamadas: list[dict] = []
        self._trava = threading.Lock()

    def gerar(self, *, modelo, sistema, mensagens, ferramentas, opcoes, ao_texto):
        chamada = {"modelo": modelo, "sistema": [b.texto for b in sistema], "mensagens": copy.deepcopy(mensagens),
                   "ferramentas": [f.nome for f in ferramentas], "opcoes": opcoes}
        with self._trava:
            self.chamadas.append(chamada)
        resposta = self.funcao(chamada)
        if resposta.texto:
            ao_texto(resposta.texto)
        return resposta


class CasoComConfig(unittest.TestCase):
    """Cria uma pasta temporária com config.toml apontando para as skills de teste."""

    toml_extra = ""
    modelo_padrao = "roteiro:principal"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def config(self, toml_extra: str = "", modelo: str | None = None):
        arquivo = self.tmp / "config.toml"
        arquivo.write_text(
            f"""
[skills]
fontes = [{{ caminho = "{FIXTURE.as_posix()}" }}]

[modelos]
padrao = "{modelo or self.modelo_padrao}"

[runtime]
banco = "dados/teste.db"
pasta_arquivos = "dados/arquivos"
max_turnos = 6
"""
            + self.toml_extra
            + toml_extra,
            encoding="utf-8",
        )
        return carregar_config(arquivo)

    def orquestrador(self, provedores: dict, toml_extra: str = "", modelo: str | None = None) -> Orquestrador:
        o = Orquestrador(self.config(toml_extra, modelo), provedores_extras=provedores)
        self.addCleanup(o.armazenamento.fechar)
        return o


class Eventos(list):
    def __call__(self, tipo: str, dados: dict) -> None:
        self.append((tipo, dados))

    def tipos(self) -> list[str]:
        return [t for t, _ in self]

    def de(self, tipo: str) -> list[dict]:
        return [d for t, d in self if t == tipo]


__all__ = [
    "CasoComConfig", "Eventos", "ErroProvedor", "FIXTURE", "ProvedorFuncao", "ProvedorRoteiro", "RAIZ",
    "ferramenta", "texto",
]
