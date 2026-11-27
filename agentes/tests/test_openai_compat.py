"""Provedor compatível com a OpenAI contra um servidor local de mentira (SSE de verdade)."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import apoio  # noqa: F401
from founders_agentes.provedores import BlocoSistema, EspecFerramenta, ErroProvedor, OpcoesChamada
from founders_agentes.provedores.openai_compat import ProvedorOpenAICompat, converter_mensagens


class ServidorFalso:
    def __init__(self, status=200, pedacos=None, corpo_erro=None):
        self.pedidos = []
        servidor = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                servidor.pedidos.append({"caminho": self.path, "cabecalhos": dict(self.headers), "corpo": corpo})
                if status != 200:
                    dados = json.dumps(corpo_erro or {}).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for pedaco in pedacos:
                    texto = pedaco if isinstance(pedaco, str) else json.dumps(pedaco)
                    self.wfile.write(f"data: {texto}\n\n".encode())
                    self.wfile.flush()

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def fechar(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def escolha(delta, fim=None):
    return {"model": "modelo-x", "choices": [{"index": 0, "delta": delta, "finish_reason": fim}]}


class TestOpenAICompat(unittest.TestCase):
    def rodar(self, servidor, mensagens=None):
        provedor = ProvedorOpenAICompat("teste", base_url=servidor.url, chave="sk-teste", cabecalhos={"X-Extra": "1"})
        textos = []
        resposta = provedor.gerar(
            modelo="modelo-x",
            sistema=[BlocoSistema("estável", cache=True), BlocoSistema("variável")],
            mensagens=mensagens or [{"role": "user", "content": "oi"}],
            ferramentas=[EspecFerramenta("ler", "lê", {"type": "object", "properties": {"c": {"type": "string"}}})],
            opcoes=OpcoesChamada(esforco="high"),
            ao_texto=textos.append,
        )
        return resposta, textos

    def test_texto_ferramenta_e_uso_em_streaming(self):
        servidor = ServidorFalso(pedacos=[
            ": keep-alive",
            escolha({"role": "assistant", "content": "Vou "}),
            escolha({"content": "ler."}),
            escolha({"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "ler", "arguments": "{\"c\":"}}]}),
            escolha({"tool_calls": [{"index": 0, "function": {"arguments": " \"x.md\"}"}}]}),
            escolha({}, "tool_calls"),
            {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 40}}},
            "[DONE]",
        ])
        self.addCleanup(servidor.fechar)
        historico = [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c0", "name": "ler", "arguments": {"c": "a"}}], "raw": {"provedor": "anthropic"}},
            {"role": "tool", "tool_call_id": "c0", "content": "conteúdo"},
            {"role": "user", "content": "e agora?"},
        ]
        resposta, textos = self.rodar(servidor, historico)
        self.assertEqual(textos, ["Vou ", "ler."])
        self.assertEqual(resposta.texto, "Vou ler.")
        self.assertEqual(resposta.motivo_parada, "ferramenta")
        self.assertEqual((resposta.chamadas[0].id, resposta.chamadas[0].argumentos), ("call_1", {"c": "x.md"}))
        self.assertEqual((resposta.uso.entrada, resposta.uso.saida, resposta.uso.cache_leitura), (50, 7, 40))
        pedido = servidor.pedidos[0]
        self.assertEqual(pedido["caminho"], "/v1/chat/completions")
        self.assertEqual(pedido["cabecalhos"]["Authorization"], "Bearer sk-teste")
        self.assertEqual(pedido["cabecalhos"]["X-Extra"], "1")
        corpo = pedido["corpo"]
        self.assertTrue(corpo["stream"])
        self.assertNotIn("reasoning_effort", corpo)
        self.assertEqual(corpo["messages"][0], {"role": "system", "content": "estável\n\nvariável"})
        self.assertEqual(corpo["messages"][2]["tool_calls"][0]["function"], {"name": "ler", "arguments": "{\"c\": \"a\"}"})
        self.assertEqual(corpo["messages"][3], {"role": "tool", "tool_call_id": "c0", "content": "conteúdo"})
        self.assertEqual(corpo["tools"][0]["function"]["name"], "ler")

    def test_chamadas_sem_indice_e_json_invalido(self):
        servidor = ServidorFalso(pedacos=[
            escolha({"tool_calls": [{"id": "a", "function": {"name": "ler", "arguments": "{\"c\": \"1\"}"}}]}),
            escolha({"tool_calls": [{"id": "b", "function": {"name": "ler", "arguments": "{quebrado"}}]}, "stop"),
            "[DONE]",
        ])
        self.addCleanup(servidor.fechar)
        resposta, _ = self.rodar(servidor)
        self.assertEqual([c.id for c in resposta.chamadas], ["a", "b"])
        self.assertEqual(resposta.chamadas[0].argumentos, {"c": "1"})
        self.assertIsNone(resposta.chamadas[1].argumentos)
        self.assertIn("JSON", resposta.chamadas[1].erro)
        self.assertEqual(resposta.motivo_parada, "ferramenta")

    def test_erro_http(self):
        servidor = ServidorFalso(status=429, corpo_erro={"error": {"message": "limite de uso"}})
        self.addCleanup(servidor.fechar)
        with self.assertRaises(ErroProvedor) as ctx:
            self.rodar(servidor)
        self.assertEqual(ctx.exception.status, 429)
        self.assertTrue(ctx.exception.repetivel)
        self.assertIn("limite de uso", str(ctx.exception))

    def test_sem_conexao(self):
        provedor = ProvedorOpenAICompat("x", base_url="http://127.0.0.1:9/v1", timeout=2)
        with self.assertRaises(ErroProvedor) as ctx:
            provedor.gerar(modelo="m", sistema=[], mensagens=[{"role": "user", "content": "oi"}], ferramentas=[], opcoes=OpcoesChamada(), ao_texto=lambda _: None)
        self.assertTrue(ctx.exception.repetivel)

    def test_corte_de_historico_no_limite_de_usuario(self):
        historico = [{"role": "user", "content": str(i)} if i % 2 == 0 else {"role": "assistant", "content": str(i)} for i in range(10)]
        cortado = converter_mensagens(historico, max_mensagens=5)
        self.assertEqual(cortado[0], {"role": "user", "content": "6"})


if __name__ == "__main__":
    unittest.main()
