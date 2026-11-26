import json
import unittest

from apoio import CasoComConfig, ErroProvedor, Eventos, ProvedorRoteiro, ferramenta, texto
from founders_agentes.agentes import RECEPCAO, ErroAgente
from founders_agentes.provedores import ChamadaFerramenta, RespostaModelo


class TestOrquestrador(CasoComConfig):
    def test_resposta_simples_persistida(self):
        roteiro = ProvedorRoteiro([texto("Sua margem é 30%.")])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        r = o.conversar("Qual minha margem?", agente="financas-teste", emitir=eventos)
        self.assertEqual(r.texto, "Sua margem é 30%.")
        self.assertIsNone(r.erro)
        self.assertEqual(eventos.tipos(), ["sessao", "agente", "texto", "fim"])
        self.assertEqual(eventos.de("fim")[0]["uso"]["entrada"], 10)
        sistema = roteiro.chamadas[0]["sistema"]
        self.assertIn('<skill id="financas-teste">', sistema[0])
        self.assertIn("ler_arquivo_skill", sistema[0])
        self.assertIn("Perfil do negócio: ainda vazio.", sistema[1])
        sessao = o.armazenamento.obter_sessao(r.sessao_id, "local")
        self.assertEqual([m["role"] for m in sessao.mensagens], ["user", "assistant"])
        self.assertEqual(sessao.agente_atual, "financas-teste")
        self.assertEqual(sessao.titulo, "Qual minha margem?")
        self.assertEqual(o.armazenamento.consumo(r.sessao_id)[0]["modelo"], "roteiro:principal")

    def test_le_arquivo_da_skill(self):
        roteiro = ProvedorRoteiro([ferramenta("ler_arquivo_skill", caminho="references/margem.md"), texto("Li a referência.")])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        o.conversar("margem?", agente="financas-teste", emitir=eventos)
        resultado = roteiro.chamadas[1]["mensagens"][-1]
        self.assertEqual(resultado["role"], "tool")
        self.assertIn("Margem de contribuição", resultado["content"])
        self.assertIn("skill://vendas-teste/SKILL.md", resultado["content"])
        self.assertFalse(resultado["is_error"])
        self.assertEqual(eventos.de("ferramenta")[0]["nome"], "ler_arquivo_skill")

    def test_passagem_da_recepcao_para_especialista(self):
        roteiro = ProvedorRoteiro([
            ferramenta("passar_para_agente", agente="financas-teste", motivo="é finanças", resumo="caixa não fecha; fatura 80 mil"),
            texto("Sou o de Finanças. Vamos ao caixa."),
            texto("Continuando com você."),
        ])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        r = o.conversar("meu caixa não fecha", emitir=eventos)
        self.assertEqual(roteiro.chamadas[0]["ferramentas"], ["atualizar_perfil", "passar_para_agente"])
        self.assertIn("Recepção", roteiro.chamadas[0]["sistema"][0])
        self.assertIn('<skill id="financas-teste">', roteiro.chamadas[1]["sistema"][0])
        transferencia = roteiro.chamadas[1]["mensagens"][-1]["content"]
        self.assertIn("caixa não fecha; fatura 80 mil", transferencia)
        passagem = eventos.de("passagem")[0]
        self.assertEqual((passagem["de"], passagem["agente"]), (RECEPCAO, "financas-teste"))
        self.assertEqual(r.agente, "financas-teste")
        self.assertEqual(r.texto, "Sou o de Finanças. Vamos ao caixa.")
        # a próxima mensagem continua com o especialista, sem passar pela Recepção
        o.conversar("e agora?", sessao_id=r.sessao_id)
        self.assertIn('<skill id="financas-teste">', roteiro.chamadas[2]["sistema"][0])

    def test_reserva_quando_o_modelo_falha(self):
        falho = ProvedorRoteiro([ErroProvedor("HTTP 529: sobrecarregado", status=529, repetivel=True)], nome="falho", texto_antes_de_falhar="Começ")
        reserva = ProvedorRoteiro([texto("Resposta da reserva.")])
        o = self.orquestrador({"falho": falho, "roteiro": reserva}, toml_extra="", modelo="falho:x")
        o.config.modelos_reserva = ["roteiro:y"]
        eventos = Eventos()
        r = o.conversar("oi", agente="vendas-teste", emitir=eventos)
        self.assertEqual(r.texto, "Resposta da reserva.")
        self.assertIn("reinicio", eventos.tipos())
        self.assertIn("Tentando roteiro:y", eventos.de("aviso")[0]["mensagem"])
        self.assertEqual(reserva.chamadas[0]["modelo"], "y")

    def test_todos_os_modelos_falham(self):
        roteiro = ProvedorRoteiro([ErroProvedor("sem chave")])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        r = o.conversar("oi", agente="vendas-teste", emitir=eventos)
        self.assertIn("sem chave", r.erro)
        self.assertEqual(eventos.de("erro")[0]["mensagem"][:23], "Nenhum modelo respondeu")
        self.assertEqual(eventos.tipos()[-1], "fim")

    def test_argumentos_invalidos_viram_erro_para_o_modelo(self):
        quebrada = RespostaModelo(texto="", chamadas=[ChamadaFerramenta("x1", "ler_arquivo_skill", None, erro="JSON cortado")], motivo_parada="ferramenta")
        roteiro = ProvedorRoteiro([
            quebrada,
            ferramenta("ler_arquivo_skill", caminho=123),
            ferramenta("ferramenta_inexistente"),
            texto("ok"),
        ])
        o = self.orquestrador({"roteiro": roteiro})
        o.conversar("margem", agente="financas-teste")
        resultados = [m for m in roteiro.chamadas[-1]["mensagens"] if m["role"] == "tool"]
        self.assertTrue(all(r["is_error"] for r in resultados))
        self.assertIn("INVALID_JSON", resultados[0]["content"])
        self.assertIn("deveria ser string", resultados[1]["content"])
        self.assertIn("desconhecida", resultados[2]["content"])

    def test_perfil_do_negocio_chega_aos_proximos_agentes(self):
        roteiro = ProvedorRoteiro([
            ferramenta("atualizar_perfil", campos={"faturamento_mensal": "R$ 80 mil", "regime": "Simples"}),
            texto("Anotado."),
            texto("Já sei do seu faturamento."),
        ])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        o.conversar("faturo 80 mil no Simples", agente="vendas-teste", emitir=eventos)
        self.assertEqual(o.armazenamento.obter_perfil("local")["regime"], "Simples")
        self.assertIn("perfil", eventos.tipos())
        o.conversar("e o caixa?", agente="financas-teste")
        self.assertIn("- faturamento_mensal: R$ 80 mil", roteiro.chamadas[2]["sistema"][1])

    def test_consulta_a_outro_agente(self):
        roteiro = ProvedorRoteiro([
            ferramenta("consultar_agente", agente="vendas-teste", pergunta="qual o funil ideal?", contexto="B2B"),
            texto("Funil em 3 etapas."),
            texto("Segundo Vendas, use 3 etapas."),
        ])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        r = o.conversar("me ajuda", agente="financas-teste", emitir=eventos)
        consulta = roteiro.chamadas[1]
        self.assertIn('<skill id="vendas-teste">', consulta["sistema"][0])
        self.assertNotIn("consultar_agente", consulta["ferramentas"])
        self.assertNotIn("passar_para_agente", consulta["ferramentas"])
        self.assertIn("Resposta de Vendas Teste", roteiro.chamadas[2]["mensagens"][-1]["content"])
        self.assertEqual(r.texto, "Segundo Vendas, use 3 etapas.")
        self.assertEqual([d["delta"] for d in eventos.de("texto")], ["Segundo Vendas, use 3 etapas."])
        self.assertEqual(eventos.de("consulta")[0]["para"], "vendas-teste")

    def test_salvar_arquivo_e_scripts_desligados(self):
        roteiro = ProvedorRoteiro([ferramenta("salvar_arquivo", nome="plano.md", conteudo="# Plano"), texto("Salvei.")])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        r = o.conversar("salva", agente="financas-teste", emitir=eventos)
        self.assertNotIn("executar_script", roteiro.chamadas[0]["ferramentas"])
        arquivo = eventos.de("arquivo")[0]
        self.assertEqual(arquivo["url"], f"/v1/sessoes/{r.sessao_id}/arquivos/plano.md")
        self.assertEqual(o.armazenamento.caminho_arquivo(r.sessao_id, "plano.md").read_text(), "# Plano")

    def test_executar_script_da_skill(self):
        roteiro = ProvedorRoteiro([
            ferramenta("salvar_arquivo", nome="dados.json", conteudo=json.dumps({"valores": [1, 2, 3.5]})),
            ferramenta("executar_script", skill="financas-teste", script="scripts/soma.py", argumentos=["dados.json"]),
            ferramenta("executar_script", skill="financas-teste", script="scripts/soma.py", argumentos=["../fora.json"]),
            ferramenta("executar_script", skill="financas-teste", script="references/margem.md"),
            texto("Total 6.5."),
        ])
        o = self.orquestrador({"roteiro": roteiro}, toml_extra="")
        o.config.runtime.permitir_scripts = True
        eventos = Eventos()
        r = o.conversar("soma", agente="financas-teste", emitir=eventos)
        self.assertIn("executar_script", roteiro.chamadas[0]["ferramentas"])
        resultados = [m for m in roteiro.chamadas[-1]["mensagens"] if m["role"] == "tool"]
        self.assertIn("total 6.5", resultados[1]["content"])
        self.assertIn("resultado.txt", resultados[1]["content"])
        self.assertTrue(resultados[2]["is_error"])
        self.assertTrue(resultados[3]["is_error"])
        self.assertEqual(o.armazenamento.caminho_arquivo(r.sessao_id, "resultado.txt").read_text(), "6.5")
        self.assertIn("resultado.txt", [a["nome"] for a in eventos.de("arquivo")])

    def test_limite_de_turnos_e_recusa(self):
        roteiro = ProvedorRoteiro([ferramenta("listar_arquivos_skill") for _ in range(6)])
        o = self.orquestrador({"roteiro": roteiro})
        eventos = Eventos()
        o.conversar("loop", agente="financas-teste", emitir=eventos)
        self.assertIn("rodadas", eventos.de("aviso")[0]["mensagem"])

        roteiro2 = ProvedorRoteiro([texto("", motivo_parada="recusa", detalhe="cyber")])
        o2 = self.orquestrador({"roteiro": roteiro2})
        eventos2 = Eventos()
        o2.conversar("algo", agente="vendas-teste", emitir=eventos2)
        self.assertEqual(eventos2.de("recusa")[0]["detalhe"], "cyber")

    def test_erros_de_entrada(self):
        o = self.orquestrador({"roteiro": ProvedorRoteiro()})
        with self.assertRaises(ErroAgente):
            o.conversar("oi", agente="so-no-code")
        with self.assertRaises(ErroAgente):
            o.conversar("oi", sessao_id="naoexiste123")
        with self.assertRaises(ValueError):
            o.conversar("   ", agente="vendas-teste")


if __name__ == "__main__":
    unittest.main()
