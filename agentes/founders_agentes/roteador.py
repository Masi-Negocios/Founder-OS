"""Sugestão rápida de agentes por palavras (sem chamar modelo).

Serve para a interface sugerir especialistas enquanto o usuário digita e para
depurar o catálogo. A escolha de verdade fica com a Recepção, que é um agente.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .agentes import Agente, RegistroAgentes
from .skills import normalizar

_PALAVRA = re.compile(r"[a-z0-9]+")
_ASPAS = re.compile(r"[\"“”]([^\"“”]{4,120})[\"“”]")
_VAZIAS = set(
    "a o e as os um uma uns umas de da do das dos em na no nas nos por para pra com sem que se ao aos "
    "meu minha meus minhas seu sua seus suas nosso nossa voce eu ele ela eles elas isso esse essa este esta "
    "como mais menos muito pouco ja nao sim ou mas quando qual quais quem onde porque pois entao "
    "use usar quando disser pedir skill skills founder founders masi negocios negocio empresa ser ter fazer faz "
    "quero preciso queria pode posso tem tenho sobre ate tambem cada todo toda todos todas".split()
)


def _termos(texto: str) -> list[str]:
    termos = []
    for palavra in _PALAVRA.findall(normalizar(texto)):
        if len(palavra) < 3 or palavra in _VAZIAS:
            continue
        if len(palavra) > 4 and palavra.endswith("s"):
            palavra = palavra[:-1]
        termos.append(palavra)
    return termos


class RoteadorLexico:
    def __init__(self, registro: RegistroAgentes) -> None:
        self.agentes = registro.especialistas()
        self._docs: list[Counter] = []
        self._gatilhos: list[list[str]] = []
        frequencia: Counter = Counter()
        for agente in self.agentes:
            texto = " ".join([agente.nome] * 3 + [agente.para_que] * 2 + [agente.descricao, agente.exemplo or ""])
            doc = Counter(_termos(texto))
            self._docs.append(doc)
            frequencia.update(set(doc))
            self._gatilhos.append([normalizar(g).strip() for g in _ASPAS.findall(agente.descricao)])
        total = max(len(self.agentes), 1)
        self._idf = {termo: math.log(1 + total / n) for termo, n in frequencia.items()}

    def sugerir(self, mensagem: str, limite: int = 5) -> list[tuple[Agente, float]]:
        termos = set(_termos(mensagem))
        alvo = normalizar(mensagem)
        pontuados = []
        for agente, doc, gatilhos in zip(self.agentes, self._docs, self._gatilhos):
            pontos = sum(self._idf.get(t, 0) * (1 + math.log(doc[t])) for t in termos if doc.get(t))
            pontos += sum(4.0 for g in gatilhos if g and g in alvo)
            if pontos > 0:
                pontuados.append((agente, round(pontos, 3)))
        pontuados.sort(key=lambda par: par[1], reverse=True)
        return pontuados[:limite]
