"""API HTTP de ponta a ponta, com o servidor de verdade numa porta local."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from apoio import CasoComConfig, ProvedorFuncao, ferramenta, texto
from founders_agentes.servidor import Aplicacao


def responder(chamada):
    ultima = chamada["mensagens"][-1]
    if "passar_para_agente" in chamada["ferramentas"] and ultima["role"] == "user" and "vendas" in ultima["content"]:
        return ferramenta("passar_para_agente", agente="vendas-teste", resumo=ultima["content"])
    if "salvar_arquivo" in chamada["ferramentas"] and ultima["role"] == "user" and "arquivo" in ultima["content"]:
        return ferramenta("salvar_arquivo", nome="resumo.md", conteudo="# Resumo")
    return texto(f"Resposta de {chamada['opcoes'].agente_id}.")


class TestServidor(CasoComConfig):
    def setUp(self):
        super().setUp()
        self.provedor = ProvedorFuncao(responder, nome="roteiro")
        self.o = self.orquestrador({"roteiro": self.provedor})
        self.o.config.servidor.chaves_api = {"segredo-a": "empresa-a", "segredo-b": "empresa-b"}
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Aplicacao(self.o, silencioso=True).classe_handler())
        self.httpd.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def pedir(self, caminho, corpo=None, chave="segredo-a", metodo=None, cabecalhos=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        pedido = urllib.request.Request(self.base + caminho, data=dados, method=metodo or ("POST" if dados else "GET"))
        if dados:
            pedido.add_header("Content-Type", "application/json")
        if chave:
            pedido.add_header("Authorization", f"Bearer {chave}")
        for k, v in (cabecalhos or {}).items():
            pedido.add_header(k, v)
        try:
            with urllib.request.urlopen(pedido, timeout=10) as resposta:
                return resposta.status, resposta.headers, resposta.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.headers, exc.read()

    def json(self, *args, **kwargs):
        status, _, corpo = self.pedir(*args, **kwargs)
        return status, json.loads(corpo)

    @staticmethod
    def eventos(bruto: bytes):
        saida = []
        for bloco in bruto.decode().split("\n\n"):
            tipo = next((l[6:].strip() for l in bloco.splitlines() if l.startswith("event:")), None)
            dados = next((l[5:].strip() for l in bloco.splitlines() if l.startswith("data:")), None)
            if tipo and dados:
                saida.append((tipo, json.loads(dados)))
        return saida

    def test_autenticacao(self):
        self.assertEqual(self.json("/saude", chave=None)[0], 200)
        status, corpo = self.json("/v1/agentes", chave=None)
        self.assertEqual((status, corpo["error"]["code"]), (401, "invalid_api_key"))
        self.assertEqual(self.json("/v1/agentes", chave="errada")[0], 401)
        status, corpo = self.json("/v1/agentes")
        self.assertEqual(status, 200)
        self.assertIn("recepcao", [a["id"] for a in corpo["agentes"]])
        self.assertEqual(corpo["areas"], ["Finanças", "Vendas"])

    def test_conversa_com_eventos_e_passagem(self):
        status, cab, bruto = self.pedir("/v1/conversa", {"mensagem": "quero falar de vendas"})
        self.assertEqual(status, 200)
        self.assertTrue(cab["Content-Type"].startswith("text/event-stream"))
        eventos = self.eventos(bruto)
        tipos = [t for t, _ in eventos]
        self.assertEqual(tipos[:3], ["sessao", "agente", "ferramenta"])
        self.assertIn("passagem", tipos)
        self.assertEqual(tipos[-1], "fim")
        texto_final = "".join(d["delta"] for t, d in eventos if t == "texto")
        self.assertEqual(texto_final, "Resposta de vendas-teste.")
        sessao_id = eventos[0][1]["sessaoId"]

        status, sessao = self.json(f"/v1/sessoes/{sessao_id}")
        self.assertEqual(status, 200)
        self.assertEqual(sessao["agenteAtual"], "vendas-teste")
        self.assertEqual([m["papel"] for m in sessao["mensagens"]], ["usuario", "agente", "agente"])
        self.assertEqual(self.json(f"/v1/sessoes/{sessao_id}", chave="segredo-b")[0], 404)
        self.assertEqual(len(self.json("/v1/sessoes")[1]["sessoes"]), 1)
        self.assertEqual(len(self.json("/v1/sessoes", chave="segredo-b")[1]["sessoes"]), 0)

    def test_conversa_sem_stream_e_arquivo(self):
        status, corpo = self.json("/v1/conversa", {"mensagem": "gera um arquivo", "agente": "financas-teste", "stream": False})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["agente"], "financas-teste")
        arquivo = next(e for e in corpo["eventos"] if e["tipo"] == "arquivo")
        status, cab, dados = self.pedir(arquivo["url"])
        self.assertEqual((status, dados), (200, b"# Resumo"))
        self.assertIn("attachment", cab["Content-Disposition"])
        self.assertEqual(self.pedir(arquivo["url"], chave="segredo-b")[0], 404)

    def test_erros_de_entrada(self):
        self.assertEqual(self.json("/v1/conversa", {"mensagem": ""})[0], 400)
        self.assertEqual(self.json("/v1/conversa", {"mensagem": "oi", "agente": "nao-existe"})[0], 404)
        self.assertEqual(self.json("/v1/conversa", {"mensagem": "oi", "agente": "so-no-code"})[0], 404)
        self.assertEqual(self.json("/v1/conversa", {"mensagem": "oi", "sessaoId": "inexistente1"})[0], 404)
        self.assertEqual(self.json("/v1/conversa", {"mensagem": "oi", "modelo": "semprovedor"})[0], 400)
        self.assertEqual(self.json("/v1/nada")[0], 404)
        self.assertEqual(self.json("/v1/agentes", {"x": 1})[0], 405)

    def test_perfil_por_dono(self):
        status, corpo = self.json("/v1/perfil", {"perfil": {"cidade": "Porto Alegre"}}, metodo="PUT")
        self.assertEqual(corpo["perfil"], {"cidade": "Porto Alegre"})
        self.assertEqual(self.json("/v1/perfil", chave="segredo-b")[1]["perfil"], {})

    def test_compativel_com_openai(self):
        status, modelos = self.json("/v1/models")
        ids = [m["id"] for m in modelos["data"]]
        self.assertEqual(ids[0], "auto")
        self.assertIn("financas-teste", ids)
        self.assertNotIn("so-no-code", ids)

        corpo = {"model": "financas-teste", "messages": [
            {"role": "system", "content": "ignorado"},
            {"role": "user", "content": "primeira"},
            {"role": "assistant", "content": "resposta antiga"},
            {"role": "user", "content": [{"type": "text", "text": "segunda"}]},
        ]}
        status, resposta = self.json("/v1/chat/completions", corpo)
        self.assertEqual(status, 200)
        self.assertEqual(resposta["object"], "chat.completion")
        self.assertEqual(resposta["choices"][0]["message"]["content"], "Resposta de financas-teste.")
        enviadas = self.provedor.chamadas[-1]["mensagens"]
        self.assertEqual([(m["role"], m["content"]) for m in enviadas],
                         [("user", "primeira"), ("assistant", "resposta antiga"), ("user", "segunda")])

        status, cab, bruto = self.pedir("/v1/chat/completions", {**corpo, "model": "auto", "stream": True,
                                                                 "messages": [{"role": "user", "content": "falar de vendas"}]})
        linhas = [l[6:] for l in bruto.decode().split("\n\n") if l.startswith("data: ")]
        self.assertEqual(linhas[-1], "[DONE]")
        pedacos = [json.loads(l) for l in linhas[:-1]]
        conteudo = "".join(p["choices"][0]["delta"].get("content", "") for p in pedacos)
        self.assertIn("Vendas Teste assumiu a conversa", conteudo)
        self.assertIn("Resposta de vendas-teste.", conteudo)
        self.assertEqual(pedacos[-1]["choices"][0]["finish_reason"], "stop")

        status, erro = self.json("/v1/chat/completions", {"model": "nao-existe", "messages": [{"role": "user", "content": "oi"}]})
        self.assertEqual((status, erro["error"]["code"]), (404, "model_not_found"))

    def test_openai_com_sessao(self):
        corpo = {"model": "financas-teste", "messages": [{"role": "user", "content": "oi"}]}
        self.json("/v1/chat/completions", corpo, cabecalhos={"X-Session-Id": "sessao-openai-1"})
        self.json("/v1/chat/completions", {**corpo, "messages": [{"role": "user", "content": "de novo"}]}, cabecalhos={"X-Session-Id": "sessao-openai-1"})
        status, sessao = self.json("/v1/sessoes/sessao-openai-1")
        self.assertEqual([m["texto"] for m in sessao["mensagens"] if m["papel"] == "usuario"], ["oi", "de novo"])
        self.assertEqual(self.json("/v1/chat/completions", corpo, chave="segredo-b", cabecalhos={"X-Session-Id": "sessao-openai-1"})[0], 404)

    def test_conselho(self):
        status, cab, bruto = self.pedir("/v1/conselho", {"pergunta": "abro filial?", "agentes": ["financas-teste", "vendas-teste"]})
        tipos = [t for t, _ in self.eventos(bruto)]
        self.assertEqual(tipos.count("membro_fim"), 2)
        self.assertEqual(tipos[-1], "fim")
        self.assertEqual(self.json("/v1/conselho", {"pergunta": "x", "agentes": ["financas-teste"]})[0], 400)
        self.assertEqual(self.json("/v1/conselho", {"pergunta": "x"})[0], 400)
        self.assertEqual(self.json("/v1/conselho", {"pergunta": "x", "agentes": ["financas-teste", "so-no-code"]})[0], 404)

    def test_interface_web(self):
        status, cab, corpo = self.pedir("/", chave=None)
        self.assertEqual(status, 200)
        self.assertIn(b"Founders OS Agentes", corpo)
        self.assertEqual(self.pedir("/web/app.js", chave=None)[0], 200)
        self.assertEqual(self.pedir("/site/icones.js", chave=None)[0], 200)
        self.assertEqual(self.pedir("/web/..%2Fconfig.toml", chave=None)[0], 404)
        self.assertEqual(self.pedir("/site/catalogo.js", chave=None)[0], 404)


if __name__ == "__main__":
    unittest.main()
