import unittest

from apoio import CasoComConfig
from founders_agentes.agentes import RECEPCAO, ErroAgente, RegistroAgentes
from founders_agentes.skills import BibliotecaSkills


class TestRegistro(CasoComConfig):
    def registro(self, toml=""):
        config = self.config(toml)
        return RegistroAgentes(BibliotecaSkills.carregar(config.fontes_skills), config)

    def test_um_agente_por_skill_mais_recepcao(self):
        reg = self.registro()
        self.assertEqual({a.id for a in reg.listar()}, {RECEPCAO, "financas-teste", "vendas-teste", "so-no-code", "sem-catalogo"})
        so_code = reg.obter("so-no-code")
        self.assertFalse(so_code.disponivel)
        self.assertIn("Claude Code", so_code.motivo_indisponivel)
        with self.assertRaises(ErroAgente):
            reg.obter_disponivel("so-no-code")
        self.assertNotIn("so-no-code", [a.id for a in reg.especialistas()])

    def test_permitir_so_claude_code_e_excluir(self):
        reg = self.registro("\n[skills.extra]\n")  # seção ignorada
        self.assertIn("sem-catalogo", reg)
        config = self.config()
        config.permitir_so_claude_code = True
        config.excluir_skills = ["sem-catalogo"]
        reg = RegistroAgentes(BibliotecaSkills.carregar(config.fontes_skills), config)
        self.assertTrue(reg.obter("so-no-code").disponivel)
        self.assertNotIn("sem-catalogo", reg)

    def test_agente_composto_sobrescrita_e_times(self):
        reg = self.registro("""
[[agentes]]
id = "cfo"
nome = "CFO"
skill_principal = "financas-teste"
skills_apoio = ["vendas-teste"]
modelo = "outro:modelo"
passa_para = ["vendas-teste"]

[[agentes]]
id = "vendas-teste"
esforco = "high"

[[agentes]]
id = "quebrado"
skill_principal = "nao-existe"

[[agentes]]
id = "recepcao"

[[times]]
id = "diretoria"
agentes = ["cfo", "vendas-teste", "fantasma"]

[[times]]
id = "pequeno"
agentes = ["cfo"]
""")
        cfo = reg.obter("cfo")
        self.assertEqual((cfo.tipo, cfo.area, cfo.modelo), ("composto", "Finanças", "outro:modelo"))
        self.assertEqual(cfo.skills, ["financas-teste", "vendas-teste"])
        self.assertEqual(reg.obter("vendas-teste").esforco, "high")
        self.assertEqual(reg.obter("vendas-teste").tipo, "skill")
        self.assertFalse(reg.obter("quebrado").disponivel)
        self.assertEqual([a.id for a in reg.destinos_de_passagem(cfo)], ["vendas-teste", RECEPCAO])
        self.assertEqual(reg.obter_time("diretoria").agentes, ["cfo", "vendas-teste"])
        with self.assertRaises(ErroAgente):
            reg.obter_time("pequeno")
        self.assertTrue(any("reservado" in a for a in reg.avisos))
        self.assertTrue(any("fantasma" in a for a in reg.avisos))

    def test_destinos_padrao(self):
        reg = self.registro()
        fin = reg.obter("financas-teste")
        destinos = [a.id for a in reg.destinos_de_passagem(fin)]
        self.assertNotIn("financas-teste", destinos)
        self.assertIn(RECEPCAO, destinos)
        self.assertNotIn(RECEPCAO, [a.id for a in reg.destinos_de_passagem(reg.obter(RECEPCAO))])


if __name__ == "__main__":
    unittest.main()
