import shutil
import tempfile
import unittest
from pathlib import Path

from apoio import FIXTURE
from founders_agentes.skills import BibliotecaSkills, ErroArquivoSkill, ErroSkill, FonteSkills


class TestBiblioteca(unittest.TestCase):
    def setUp(self):
        self.bib = BibliotecaSkills.carregar([FonteSkills(FIXTURE)])

    def test_descobre_pelo_marketplace_na_ordem_do_catalogo(self):
        self.assertEqual([s.id for s in self.bib], ["financas-teste", "vendas-teste", "so-no-code", "sem-catalogo"])
        self.assertEqual(self.bib.areas, ["Finanças", "Vendas"])
        self.assertEqual(self.bib.avisos, [])

    def test_catalogo_e_frontmatter(self):
        fin = self.bib.obter("financas-teste")
        self.assertEqual((fin.nome, fin.area, fin.icone), ("Finanças Teste", "Finanças", "banknote"))
        self.assertIn('"meu caixa não fecha"', fin.descricao)
        self.assertEqual(fin.scripts, ["scripts/soma.py"])
        vendas = self.bib.obter("vendas-teste")
        self.assertEqual(vendas.metadata, {"version": "1.0.0", "tags": ["vendas", "funil"]})
        sem = self.bib.obter("sem-catalogo")
        self.assertEqual(sem.nome, "Sem Catalogo")
        self.assertEqual(sem.descricao, "Skill fora do catálogo. Segunda linha literal.")
        self.assertEqual(self.bib.obter("so-no-code").onde, "Claude Code")

    def test_reescreve_caminhos_do_plugin(self):
        vendas = self.bib.obter("vendas-teste")
        self.assertIn("skill://financas-teste/references/margem.md", vendas.corpo)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", vendas.corpo)
        texto = self.bib.obter("financas-teste").ler_texto("references/margem.md")
        self.assertIn("skill://vendas-teste/SKILL.md", texto)

    def test_resolver(self):
        skill, rel = self.bib.resolver("skill://financas-teste/references/margem.md")
        self.assertEqual((skill.id, rel), ("financas-teste", "references/margem.md"))
        skill, rel = self.bib.resolver("references/margem.md", "financas-teste")
        self.assertEqual(skill.id, "financas-teste")
        skill, rel = self.bib.resolver("financas-teste/references/margem.md", "vendas-teste")
        self.assertEqual((skill.id, rel), ("financas-teste", "references/margem.md"))
        with self.assertRaises(ErroArquivoSkill):
            self.bib.resolver("references/margem.md")
        with self.assertRaises(ErroSkill):
            self.bib.obter("nao-existe")

    def test_nao_sai_da_pasta_da_skill(self):
        fin = self.bib.obter("financas-teste")
        for caminho in ("../vendas-teste/SKILL.md", "/etc/passwd", "references/../../vendas-teste/SKILL.md"):
            with self.assertRaises(ErroArquivoSkill):
                fin.ler_texto(caminho)
        with self.assertRaises(ErroArquivoSkill):
            fin.ler_texto("references/nao-existe.md")

    def test_binario_e_fontes_problematicas(self):
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "skills"
            shutil.copytree(FIXTURE / "plugins" / "demo" / "skills", copia)
            (copia / "financas-teste" / "assets").mkdir()
            (copia / "financas-teste" / "assets" / "modelo.xlsx").write_bytes(b"PK\x03\x04\x00\xff")
            bib = BibliotecaSkills.carregar([FonteSkills(copia), FonteSkills(copia), FonteSkills(Path(tmp) / "nada")])
            self.assertIn("arquivo binário", bib.obter("financas-teste").ler_texto("assets/modelo.xlsx"))
            self.assertEqual(len(bib), 4)
            self.assertTrue(any("repetida" in a for a in bib.avisos))
            self.assertTrue(any("não existe" in a for a in bib.avisos))


if __name__ == "__main__":
    unittest.main()
