import unittest

from apoio import CasoComConfig, Eventos, ProvedorFuncao, texto
from founders_agentes.conselho import realizar_conselho
from founders_agentes.roteador import RoteadorLexico


def responder(chamada):
    agente = chamada["opcoes"].agente_id
    if agente == "conselho":
        material = chamada["mensagens"][-1]["content"]
        return texto("Síntese: " + ("ok" if "Finanças Teste" in material and "Vendas Teste" in material else "faltou alguém"))
    return texto(f"Opinião de {agente}.")


class TestConselho(CasoComConfig):
    def test_membros_em_paralelo_e_sintese(self):
        provedor = ProvedorFuncao(responder, nome="roteiro")
        o = self.orquestrador({"roteiro": provedor})
        eventos = Eventos()
        r = realizar_conselho(o, "Abro uma filial?", agentes=["financas-teste", "vendas-teste"], emitir=eventos)
        self.assertEqual(r.texto, "Síntese: ok")
        self.assertEqual({d["agente"] for d in eventos.de("membro_fim")}, {"financas-teste", "vendas-teste"})
        self.assertEqual(eventos.de("fim")[-1]["sessaoId"], r.sessao_id)
        moderador = next(c for c in provedor.chamadas if c["opcoes"].agente_id == "conselho")
        self.assertEqual(moderador["ferramentas"], [])
        self.assertIn("modera o conselho", moderador["sistema"][0])
        sessao = o.armazenamento.obter_sessao(r.sessao_id, "local")
        self.assertEqual([m["role"] for m in sessao.mensagens], ["user", "assistant"])
        self.assertEqual(set(sessao.mensagens[1]["conselho"]), {"financas-teste", "vendas-teste"})
        self.assertEqual(sum(c["entrada"] for c in o.armazenamento.consumo(r.sessao_id)), 30)

    def test_validacoes(self):
        o = self.orquestrador({"roteiro": ProvedorFuncao(responder)})
        with self.assertRaises(ValueError):
            realizar_conselho(o, "x", agentes=["financas-teste"])
        with self.assertRaises(ValueError):
            realizar_conselho(o, "  ", agentes=["financas-teste", "vendas-teste"])


class TestRoteador(CasoComConfig):
    def test_sugere_pelo_gatilho_e_pelas_palavras(self):
        o = self.orquestrador({})
        roteador = RoteadorLexico(o.registro)
        self.assertEqual(roteador.sugerir("Socorro, meu caixa não fecha!")[0][0].id, "financas-teste")
        self.assertEqual(roteador.sugerir("preciso montar o funil de vendas")[0][0].id, "vendas-teste")
        self.assertEqual(roteador.sugerir("xyz abc"), [])


if __name__ == "__main__":
    unittest.main()
