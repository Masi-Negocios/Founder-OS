"""Provedor de demonstração: responde sem chamar nenhuma IA.

Serve para testar a interface, a API e o fluxo entre agentes sem chave de API.
Escreva "@<id-do-agente>" na mensagem para ver uma passagem de conversa.
"""
from __future__ import annotations

import re
import time
from typing import Callable

from .base import BlocoSistema, ChamadaFerramenta, EspecFerramenta, OpcoesChamada, RespostaModelo, Uso

_MENCAO = re.compile(r"@([a-z0-9][a-z0-9-]+)")


class ProvedorDemo:
    def __init__(self, nome: str = "demo", pausa: float = 0.01) -> None:
        self.nome = nome
        self.pausa = pausa
        self._contador = 0

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
        ultima = mensagens[-1] if mensagens else {}
        nomes = {f.nome: f for f in ferramentas}
        if ultima.get("role") == "user" and "passar_para_agente" in nomes:
            destinos = nomes["passar_para_agente"].parametros["properties"]["agente"].get("enum", [])
            mencao = next((m for m in _MENCAO.findall(ultima.get("content", "")) if m in destinos), None)
            if mencao:
                self._contador += 1
                return RespostaModelo(
                    texto="",
                    chamadas=[ChamadaFerramenta(
                        id=f"demo_{self._contador}",
                        nome="passar_para_agente",
                        argumentos={"agente": mencao, "motivo": "pedido do usuário", "resumo": ultima.get("content", "")},
                    )],
                    motivo_parada="ferramenta",
                    modelo=modelo,
                )
        pedido = next((m.get("content", "") for m in reversed(mensagens) if m.get("role") == "user"), "")
        if ultima.get("role") == "tool":
            texto = f"Olá! Sou {opcoes.agente_nome or 'o agente'} e assumi a conversa. Vamos continuar daqui."
        else:
            texto = (
                f"**{opcoes.agente_nome or 'Agente'}** (modo demonstração: nenhum modelo de IA conectado).\n\n"
                f"Recebi: “{pedido[:300]}”.\n\n"
                "Para respostas de verdade, defina a chave de um provedor (por exemplo ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY ou OPENROUTER_API_KEY) e escolha o modelo na configuração."
            )
        for palavra in re.split(r"(\s+)", texto):
            if palavra:
                ao_texto(palavra)
                if self.pausa:
                    time.sleep(self.pausa)
        return RespostaModelo(texto=texto, motivo_parada="fim", uso=Uso(entrada=len(pedido) // 4, saida=len(texto) // 4), modelo=modelo)
