import unittest

import apoio  # noqa: F401 - ajusta o sys.path
from founders_agentes.frontmatter import ErroFrontmatter, ler_yaml, separar_frontmatter


class TestFrontmatter(unittest.TestCase):
    def test_dobrado_e_literal(self):
        meta = ler_yaml("a: >-\n  linha um\n  linha dois\n\n  paragrafo\nb: |\n  x\n  y\n")
        self.assertEqual(meta["a"], "linha um linha dois\nparagrafo")
        self.assertEqual(meta["b"], "x\ny\n")

    def test_aspas_duplas_com_escapes(self):
        meta = ler_yaml('d: "Diz \\"oi\\".\\nFim \\u00e9"')
        self.assertEqual(meta["d"], 'Diz "oi".\nFim é')

    def test_aspas_simples_e_multilinha(self):
        meta = ler_yaml("s: 'it''s'\nm: \"começa\n  e continua\"")
        self.assertEqual(meta["s"], "it's")
        self.assertEqual(meta["m"], "começa e continua")

    def test_mapas_listas_e_tipos(self):
        meta = ler_yaml(
            "metadata:\n  version: \"1.0.0\"\n  ativo: true\n  n: 3\n"
            "tags: [a, b]\n"
            "ferramentas:\n  - Read\n  - Write\n"
            "itens:\n  - nome: x\n    valor: 1\n  - nome: y\n"
            "# comentário\n"
            "vazio:\n"
        )
        self.assertEqual(meta["metadata"], {"version": "1.0.0", "ativo": True, "n": 3})
        self.assertEqual(meta["tags"], ["a", "b"])
        self.assertEqual(meta["ferramentas"], ["Read", "Write"])
        self.assertEqual(meta["itens"], [{"nome": "x", "valor": 1}, {"nome": "y"}])
        self.assertIsNone(meta["vazio"])

    def test_escalar_simples_em_varias_linhas(self):
        meta = ler_yaml("description: Uma descrição longa\n  que continua aqui # com comentário\nname: x")
        self.assertEqual(meta["description"], "Uma descrição longa que continua aqui")
        self.assertEqual(meta["name"], "x")

    def test_separar(self):
        meta, corpo = separar_frontmatter("---\nname: a\n---\n\n# Título\n")
        self.assertEqual(meta, {"name": "a"})
        self.assertEqual(corpo, "# Título\n")
        self.assertEqual(separar_frontmatter("# só corpo"), ({}, "# só corpo"))

    def test_erros(self):
        with self.assertRaises(ErroFrontmatter):
            separar_frontmatter("---\nname: a\n")
        with self.assertRaises(ErroFrontmatter):
            ler_yaml("isto não é chave")
        with self.assertRaises(ErroFrontmatter):
            ler_yaml('a: "sem fim')


if __name__ == "__main__":
    unittest.main()
