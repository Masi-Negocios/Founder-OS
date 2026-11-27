"""Provedor Claude com um cliente falso no lugar do SDK (sem rede)."""
import unittest
from types import SimpleNamespace as NS

import apoio  # noqa: F401
from founders_agentes.provedores import BlocoSistema, EspecFerramenta, ErroProvedor, OpcoesChamada
from founders_agentes.provedores.claude import ProvedorClaude, assinatura_prefixo, converter_mensagens


class Bloco(dict):
    def to_dict(self):
        return dict(self)


class FluxoFalso:
    def __init__(self, eventos, final, erro=None):
        self.eventos, self.final, self.erro = eventos, final, erro

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for evento in self.eventos:
            yield evento
        if self.erro:
            raise self.erro

    def get_final_message(self):
        return self.final


class ClienteFalso:
    def __init__(self, fluxo):
        self.chamadas = []
        cliente = self

        class Mensagens:
            def __init__(self, beta):
                self.beta = beta

            def stream(self, **kwargs):
                cliente.chamadas.append({"beta": self.beta, **kwargs})
                return fluxo

        self.messages = Mensagens(False)
        self.beta = NS(messages=Mensagens(True))


def final_com(blocos, stop="end_turn"):
    return NS(
        content=[Bloco(b) for b in blocos],
        stop_reason=stop,
        stop_details=None,
        usage=NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=80, cache_creation_input_tokens=None),
        model="claude-opus-5-5",
    )


SISTEMA = [BlocoSistema("instruções estáveis", cache=True), BlocoSistema("data de hoje")]
FERRAMENTAS = [
    EspecFerramenta("zeta", "z", {"type": "object", "properties": {}}),
    EspecFerramenta("alfa", "a", {"type": "object", "properties": {}}),
]


class TestProvedorClaude(unittest.TestCase):
    def gerar(self, provedor, modelo="claude-opus-5-5", mensagens=None, esforco="high"):
        textos = []
        resposta = provedor.gerar(
            modelo=modelo, sistema=SISTEMA, mensagens=mensagens or [{"role": "user", "content": "oi"}],
            ferramentas=FERRAMENTAS, opcoes=OpcoesChamada(esforco=esforco), ao_texto=textos.append,
        )
        return resposta, textos

    def test_parametros_do_pedido_no_opus(self):
        eventos = [NS(type="content_block_delta", delta=NS(type="text_delta", text="Olá")),
                   NS(type="content_block_delta", delta=NS(type="input_json_delta", partial_json="{"))]
        cliente = ClienteFalso(FluxoFalso(eventos, final_com([{"type": "text", "text": "Olá", "citations": None}])))
        resposta, textos = self.gerar(ProvedorClaude(cliente=cliente))
        pedido = cliente.chamadas[0]
        self.assertTrue(pedido["beta"])
        self.assertEqual(pedido["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(pedido["fallbacks"], "default")
        self.assertEqual(pedido["thinking"], {"type": "adaptive"})
        self.assertEqual(pedido["output_config"], {"effort": "high"})
        self.assertEqual(pedido["cache_control"], {"type": "ephemeral"})
        self.assertEqual(pedido["system"][0], {"type": "text", "text": "instruções estáveis", "cache_control": {"type": "ephemeral"}})
        self.assertNotIn("cache_control", pedido["system"][1])
        self.assertEqual([t["name"] for t in pedido["tools"]], ["alfa", "zeta"])
        self.assertTrue(all(t["eager_input_streaming"] for t in pedido["tools"]))
        self.assertEqual(textos, ["Olá"])
        self.assertEqual(resposta.texto, "Olá")
        self.assertEqual((resposta.uso.entrada, resposta.uso.cache_leitura, resposta.uso.cache_escrita), (100, 80, 0))
        self.assertEqual(resposta.raw["content"], [{"type": "text", "text": "Olá"}])

    def test_modelo_antigo_sem_beta_nem_pensamento(self):
        cliente = ClienteFalso(FluxoFalso([], final_com([{"type": "text", "text": "x"}])))
        self.gerar(ProvedorClaude(cliente=cliente), modelo="claude-haiku-4-5")
        pedido = cliente.chamadas[0]
        self.assertFalse(pedido["beta"])
        self.assertNotIn("thinking", pedido)
        self.assertNotIn("output_config", pedido)

    def test_chamada_de_ferramenta_e_recusa(self):
        blocos = [{"type": "thinking", "thinking": "", "signature": "sig"},
                  {"type": "tool_use", "id": "toolu_1", "name": "alfa", "input": {"a": 1}}]
        cliente = ClienteFalso(FluxoFalso([], final_com(blocos, stop="tool_use")))
        resposta, _ = self.gerar(ProvedorClaude(cliente=cliente))
        self.assertEqual(resposta.motivo_parada, "ferramenta")
        self.assertEqual((resposta.chamadas[0].id, resposta.chamadas[0].argumentos), ("toolu_1", {"a": 1}))
        self.assertEqual(resposta.raw["assinatura"], assinatura_prefixo(SISTEMA, FERRAMENTAS))

        recusa = final_com([], stop="refusal")
        recusa.stop_details = NS(category="cyber", explanation=None)
        resposta, _ = self.gerar(ProvedorClaude(cliente=ClienteFalso(FluxoFalso([], recusa))))
        self.assertEqual((resposta.motivo_parada, resposta.detalhe), ("recusa", "cyber"))

    def test_erros_viram_erro_de_provedor(self):
        for erro, repetivel in ((RuntimeError("caiu"), False), (ValueError("json ruim"), True)):
            cliente = ClienteFalso(FluxoFalso([], None, erro=erro))
            with self.assertRaises(ErroProvedor) as ctx:
                self.gerar(ProvedorClaude(cliente=cliente))
            self.assertEqual(ctx.exception.repetivel, repetivel)


class TestConversao(unittest.TestCase):
    def test_resultados_juntos_e_raciocinio_preservado_ou_removido(self):
        raw = {"provedor": "anthropic", "assinatura": "A", "content": [
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "tool_use", "id": "toolu_1", "name": "alfa", "input": {}},
            {"type": "tool_use", "id": "toolu_2", "name": "zeta", "input": {}},
        ]}
        historico = [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "", "tool_calls": [], "raw": raw},
            {"role": "tool", "tool_call_id": "toolu_1", "content": "r1", "is_error": False},
            {"role": "tool", "tool_call_id": "toolu_2", "content": "r2", "is_error": True},
            {"role": "user", "content": "e agora?"},
        ]
        mesma = converter_mensagens(historico, "A", "anthropic")
        self.assertEqual([m["role"] for m in mesma], ["user", "assistant", "user"])
        self.assertEqual(mesma[1]["content"][0]["type"], "thinking")
        self.assertEqual([b["type"] for b in mesma[2]["content"]], ["tool_result", "tool_result", "text"])
        self.assertTrue(mesma[2]["content"][1]["is_error"])
        outra = converter_mensagens(historico, "B", "anthropic")
        self.assertEqual([b["type"] for b in outra[1]["content"]], ["tool_use", "tool_use"])
        self.assertEqual(raw["content"][0]["type"], "thinking")  # o histórico original não muda

    def test_mensagem_de_outro_provedor(self):
        historico = [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "vou ler", "tool_calls": [{"id": "call:1/x", "name": "alfa", "arguments": {"q": 1}}]},
            {"role": "tool", "tool_call_id": "call:1/x", "content": "ok"},
            {"role": "assistant", "content": "", "tool_calls": []},
        ]
        saida = converter_mensagens(historico, "A", "anthropic")
        self.assertEqual(saida[1]["content"][1], {"type": "tool_use", "id": "call_1_x", "name": "alfa", "input": {"q": 1}})
        self.assertEqual(saida[2]["content"][0]["tool_use_id"], "call_1_x")
        self.assertEqual(saida[3]["content"], [{"type": "text", "text": "(sem resposta)"}])


if __name__ == "__main__":
    unittest.main()
