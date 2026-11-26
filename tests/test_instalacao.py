import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import instalar


class InstalacaoPorProjeto(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.projeto = Path(temporario.name, "Meu projeto").resolve()
        self.projeto.mkdir()

    def cli(self, *args, sucesso=True):
        resultado = subprocess.run(
            [sys.executable, str(instalar.RAIZ / "scripts/instalar.py"), *args],
            cwd=self.projeto, capture_output=True, text=True,
        )
        self.assertEqual(resultado.returncode == 0, sucesso, resultado.stdout + resultado.stderr)
        return resultado

    def test_catalogo_completo_e_perfis_dos_dois_clientes(self):
        self.cli()
        self.cli("--ambiente", "opencode")
        raiz = self.projeto / ".agents/skills"
        self.assertEqual({p.name for p in raiz.iterdir()}, set(instalar.catalogo()))
        for arquivo in instalar.SKILLS.rglob("*"):
            if arquivo.is_file():
                self.assertEqual((raiz / arquivo.relative_to(instalar.SKILLS)).read_bytes(), arquivo.read_bytes())

        for s in instalar.catalogo().values():
            if "agente" not in s:
                continue
            nome = s["agente"]
            caminho = f".agents/skills/{s['id']}/SKILL.md"
            self.assertTrue((self.projeto / caminho).is_file())
            codex = (self.projeto / f".codex/agents/{nome}.toml").read_text(encoding="utf-8")
            campos = dict(linha.split(" = ", 1) for linha in codex.splitlines())
            self.assertEqual(json.loads(campos["name"]), nome)
            self.assertIn(caminho, json.loads(campos["developer_instructions"]))
            outro = (self.projeto / f".opencode/agents/{nome}.md").read_text(encoding="utf-8")
            self.assertIn("\nmode: subagent\n", outro)
            self.assertIn(caminho, outro)
        self.assertIn("0 arquivos gravados", self.cli().stdout)

    def test_selecao_repetivel_e_recursos_da_maquina(self):
        self.cli("--skill", "buscar-temas", "--skill", "diretor-financeiro-masinegocios")
        raiz = self.projeto / ".agents/skills"
        self.assertEqual({p.name for p in raiz.iterdir()}, {
            "buscar-temas", "configurar-maquina", "criar-hooks", "maquina-de-carrosseis",
            "storyteller-carrossel", "diretor-financeiro-masinegocios",
        })
        referencia = raiz / "maquina-de-carrosseis/references"
        self.assertTrue((referencia / "../../configurar-maquina/assets/maquina-de-carrosseis.html").is_file())
        self.assertTrue((raiz / "diretor-financeiro-masinegocios/references/guia-de-voz-masi-negocios.md").is_file())
        self.assertEqual([p.name for p in (self.projeto / ".codex/agents").iterdir()], ["masi-financeiro.toml"])

    def test_consulta_e_id_invalido_preservam_o_projeto(self):
        self.assertIn("masi-comercial", self.cli("--listar").stdout)
        self.cli("--skill", "../fora", sucesso=False)
        self.assertEqual(list(self.projeto.iterdir()), [])

    def test_colisao_antes_da_primeira_escrita(self):
        agente = self.projeto / ".codex/agents/masi-financeiro.toml"
        agente.parent.mkdir(parents=True)
        agente.write_text("meu agente", encoding="utf-8")
        self.cli("--skill", "diretor-financeiro-masinegocios", sucesso=False)
        self.assertEqual(agente.read_text(encoding="utf-8"), "meu agente")
        self.assertFalse((self.projeto / ".agents/skills").exists())
        self.assertFalse((self.projeto / instalar.REGISTRO).exists())

    def test_atualizacao_remocao_e_edicao_local(self):
        gerencia = lambda _: True
        base = ".agents/skills/exemplo/"
        principal, antigo, novo = (base + n for n in ["SKILL.md", "references/antigo.md", "assets/novo.txt"])
        instalar.sincronizar(self.projeto, {principal: b"v1", antigo: b"A"}, gerencia)
        instalar.sincronizar(self.projeto, {principal: b"v2", novo: b"B"}, gerencia)
        self.assertFalse((self.projeto / antigo).exists())
        self.assertEqual((self.projeto / principal).read_bytes(), b"v2")
        local = self.projeto / (base + "meu-material.txt")
        local.write_text("meu")
        (self.projeto / novo).write_bytes(b"edicao")
        self.cli("--remover", sucesso=False)
        self.assertTrue((self.projeto / principal).exists())
        self.assertEqual((self.projeto / novo).read_bytes(), b"edicao")
        (self.projeto / novo).write_bytes(b"B")
        self.cli("--remover")
        self.cli("--remover")
        self.assertEqual(local.read_text(), "meu")
        self.assertFalse((self.projeto / principal).exists())
        self.assertFalse((self.projeto / instalar.REGISTRO).exists())

    def test_retomada_apos_interrupcao(self):
        arquivos = {".agents/skills/a/SKILL.md": b"a", ".agents/skills/b/SKILL.md": b"b"}
        original = instalar.gravar

        def interromper(caminho, dados):
            if caminho.parent.name == "b":
                raise OSError("gravação interrompida")
            original(caminho, dados)

        with patch.object(instalar, "gravar", interromper), self.assertRaises(OSError):
            instalar.sincronizar(self.projeto, arquivos, lambda _: True)
        instalar.sincronizar(self.projeto, arquivos, lambda _: True)
        for nome, dados in arquivos.items():
            self.assertEqual((self.projeto / nome).read_bytes(), dados)
        self.cli("--remover")
        self.assertFalse((self.projeto / ".agents/skills").exists())

    def test_preserva_destino_de_link(self):
        fora = self.projeto.parent / "fora"
        fora.mkdir()
        (self.projeto / ".agents").mkdir()
        try:
            (self.projeto / ".agents/skills").symlink_to(fora, target_is_directory=True)
        except OSError:
            self.skipTest("Links indisponíveis neste sistema")
        self.cli("--skill", "boas-vindas", sucesso=False)
        self.assertEqual(list(fora.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
