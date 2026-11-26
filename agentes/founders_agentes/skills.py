"""Biblioteca de Skills: descobre, lê e indexa Skills no formato Claude (SKILL.md).

As Skills continuam sendo a fonte única das instruções. Esta camada só as lê:
nada aqui altera os arquivos em plugins/.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import ErroFrontmatter, separar_frontmatter

URI_SKILL = "skill://"
MAX_CARACTERES_LEITURA = 150_000
_RAIZ_PLUGIN_SKILLS = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/")
_RAIZ_PLUGIN = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/?")
_PASTA_SKILL = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/?")
_EXTENSOES_TEXTO = {
    "", ".md", ".txt", ".py", ".json", ".js", ".cjs", ".mjs", ".ts", ".html", ".css",
    ".csv", ".tsv", ".yaml", ".yml", ".toml", ".sh", ".swift", ".xml", ".svg",
}
_IGNORAR = {".DS_Store", "__pycache__", "node_modules", ".git", ".venv"}
_MAX_ARQUIVOS_LISTADOS = 300


class ErroSkill(Exception):
    """Skill inexistente ou inválida."""


class ErroArquivoSkill(ErroSkill):
    """Arquivo de skill inexistente, fora da pasta da skill ou ilegível."""


@dataclass
class FonteSkills:
    """Uma pasta de onde vêm Skills: raiz de marketplace, plugin, pasta de skills ou uma skill."""

    caminho: Path
    catalogo: Path | None = None
    rotulo: str | None = None
    excluir: tuple[str, ...] = ()


@dataclass
class Skill:
    id: str
    nome_tecnico: str
    descricao: str
    corpo: str
    raiz: Path
    fonte: str
    metadata: dict = field(default_factory=dict)
    compatibilidade: str | None = None
    catalogo: dict = field(default_factory=dict)
    arquivos: list[str] = field(default_factory=list)
    ordem: int = 10_000

    @property
    def nome(self) -> str:
        return self.catalogo.get("nome") or self.catalogo.get("name") or _humanizar(self.id)

    @property
    def area(self) -> str | None:
        return self.catalogo.get("area")

    @property
    def para_que(self) -> str:
        return self.catalogo.get("paraQue") or self.catalogo.get("summary") or _primeira_frase(self.descricao)

    @property
    def exemplo(self) -> str | None:
        return self.catalogo.get("exemplo") or self.catalogo.get("example")

    @property
    def icone(self) -> str | None:
        return self.catalogo.get("icone") or self.catalogo.get("icon")

    @property
    def onde(self) -> str | None:
        """Ambiente exigido pela skill, se houver (ex.: "Claude Code")."""
        return self.catalogo.get("onde")

    @property
    def scripts(self) -> list[str]:
        return [a for a in self.arquivos if a.startswith("scripts/") and a.endswith(".py")]

    def reescrever_caminhos(self, texto: str) -> str:
        """Troca as variáveis de caminho do Claude por URIs skill:// que as ferramentas entendem."""
        texto = _RAIZ_PLUGIN_SKILLS.sub(URI_SKILL, texto)
        texto = _PASTA_SKILL.sub(f"{URI_SKILL}{self.id}/", texto)
        return _RAIZ_PLUGIN.sub(URI_SKILL, texto)

    def caminho(self, relativo: str) -> Path:
        rel = relativo.strip().replace("\\", "/")
        while rel.startswith("./"):
            rel = rel[2:]
        rel = rel.lstrip("/")
        if not rel:
            raise ErroArquivoSkill("caminho vazio")
        raiz = self.raiz.resolve()
        alvo = (raiz / rel).resolve()
        if alvo != raiz and raiz not in alvo.parents:
            raise ErroArquivoSkill(f"caminho fora da skill {self.id}: {relativo}")
        return alvo

    def ler_texto(self, relativo: str, max_caracteres: int = MAX_CARACTERES_LEITURA) -> str:
        alvo = self.caminho(relativo)
        if not alvo.is_file():
            raise ErroArquivoSkill(f"arquivo não encontrado na skill {self.id}: {relativo}")
        tamanho = alvo.stat().st_size
        if alvo.suffix.lower() not in _EXTENSOES_TEXTO:
            return f"[arquivo binário {alvo.name}, {tamanho} bytes: não dá para ler como texto]"
        try:
            texto = alvo.read_text("utf-8")
        except UnicodeDecodeError:
            return f"[arquivo binário {alvo.name}, {tamanho} bytes: não dá para ler como texto]"
        texto = self.reescrever_caminhos(texto)
        if len(texto) > max_caracteres:
            texto = texto[:max_caracteres] + f"\n\n[... arquivo cortado: {len(texto)} caracteres no total]"
        return texto

    def resumo_publico(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "area": self.area,
            "icone": self.icone,
            "paraQue": self.para_que,
            "exemplo": self.exemplo,
            "descricao": self.descricao,
            "onde": self.onde,
            "arquivos": self.arquivos,
            "fonte": self.fonte,
        }


class BibliotecaSkills:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self.areas: list[str] = []
        self.avisos: list[str] = []

    @classmethod
    def carregar(cls, fontes: list[FonteSkills]) -> "BibliotecaSkills":
        biblioteca = cls()
        for fonte in fontes:
            biblioteca.adicionar_fonte(fonte)
        return biblioteca

    def adicionar_fonte(self, fonte: FonteSkills) -> None:
        raiz = Path(fonte.caminho).expanduser()
        if not raiz.exists():
            self.avisos.append(f"fonte de skills não existe: {raiz}")
            return
        catalogo = self._ler_catalogo(fonte, raiz)
        rotulo = fonte.rotulo or raiz.resolve().name
        for pasta in descobrir_pastas_de_skills(raiz):
            sid = pasta.name
            if sid in fonte.excluir:
                continue
            if sid in self._skills:
                self.avisos.append(f"skill '{sid}' repetida em {rotulo}; mantida a de {self._skills[sid].fonte}")
                continue
            try:
                skill = ler_pasta_skill(pasta, rotulo, catalogo.get(sid, {}))
            except (OSError, ErroFrontmatter, UnicodeDecodeError) as exc:
                self.avisos.append(f"{sid}: {exc}")
                continue
            self._skills[sid] = skill
        self._skills = dict(sorted(self._skills.items(), key=lambda kv: (kv[1].ordem, kv[0])))

    def _ler_catalogo(self, fonte: FonteSkills, raiz: Path) -> dict[str, dict]:
        caminho = fonte.catalogo
        if caminho is None:
            for nome in ("catalogo.json", "catalog.json"):
                if (raiz / nome).is_file():
                    caminho = raiz / nome
                    break
        if caminho is None:
            return {}
        try:
            dados = json.loads(Path(caminho).read_text("utf-8"))
        except (OSError, ValueError) as exc:
            self.avisos.append(f"catálogo ilegível {caminho}: {exc}")
            return {}
        itens = dados.get("skills", []) if isinstance(dados, dict) else dados
        if isinstance(dados, dict):
            for area in dados.get("areas") or []:
                if area not in self.areas:
                    self.areas.append(area)
        resultado: dict[str, dict] = {}
        for posicao, item in enumerate(itens or []):
            if isinstance(item, dict) and item.get("id"):
                resultado[item["id"]] = {**item, "_ordem": posicao}
        return resultado

    def __contains__(self, sid: object) -> bool:
        return sid in self._skills

    def __iter__(self):
        return iter(self._skills.values())

    def __len__(self) -> int:
        return len(self._skills)

    def obter(self, sid: str) -> Skill:
        try:
            return self._skills[sid]
        except KeyError:
            raise ErroSkill(f"skill não encontrada: {sid}") from None

    def resolver(self, caminho: str, skill_padrao: str | None = None) -> tuple[Skill, str]:
        """Resolve skill://<id>/<arquivo>, <id>/<arquivo> ou <arquivo> (na skill padrão)."""
        texto = caminho.strip()
        if texto.startswith(URI_SKILL):
            sid, _, rel = texto[len(URI_SKILL):].partition("/")
            if sid == "skills":
                sid, _, rel = rel.partition("/")
            return self.obter(sid), rel
        if texto.startswith("skills/"):
            texto = texto[len("skills/"):]
        primeiro, _, resto = texto.partition("/")
        if primeiro in self._skills and resto:
            padrao = self._skills.get(skill_padrao or "")
            if padrao is None or not padrao.caminho(texto).exists():
                return self._skills[primeiro], resto
        if skill_padrao:
            return self.obter(skill_padrao), texto
        raise ErroArquivoSkill("informe a skill do arquivo (ou use skill://<skill>/<arquivo>)")


def descobrir_pastas_de_skills(raiz: Path) -> list[Path]:
    """Acha as pastas de skill a partir de um marketplace, plugin, pasta de skills ou skill."""
    if (raiz / "SKILL.md").is_file():
        return [raiz]
    plugins: list[Path] = []
    marketplace = raiz / ".claude-plugin" / "marketplace.json"
    if marketplace.is_file():
        try:
            dados = json.loads(marketplace.read_text("utf-8"))
        except (OSError, ValueError):
            dados = {}
        raiz_resolvida = raiz.resolve()
        for plugin in dados.get("plugins") or []:
            origem = plugin.get("source") if isinstance(plugin, dict) else None
            if isinstance(origem, str) and "://" not in origem:
                pasta = (raiz / origem).resolve()
                if pasta == raiz_resolvida or raiz_resolvida in pasta.parents:
                    plugins.append(pasta)
    if not plugins:
        if (raiz / "skills").is_dir():
            plugins.append(raiz)
        elif (raiz / "plugins").is_dir():
            plugins.extend(sorted(p for p in (raiz / "plugins").iterdir() if (p / "skills").is_dir()))
    pastas = [p / "skills" for p in plugins] if plugins else [raiz]
    encontradas: list[Path] = []
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for filho in sorted(pasta.iterdir()):
            if filho.is_dir() and (filho / "SKILL.md").is_file():
                encontradas.append(filho)
    return encontradas


def ler_pasta_skill(pasta: Path, fonte: str, catalogo: dict) -> Skill:
    meta, corpo = separar_frontmatter((pasta / "SKILL.md").read_text("utf-8"))
    metadata = meta.get("metadata")
    skill = Skill(
        id=pasta.name,
        nome_tecnico=str(meta.get("name") or pasta.name).strip(),
        descricao=" ".join(str(meta.get("description") or "").split()),
        corpo="",
        raiz=pasta.resolve(),
        fonte=fonte,
        metadata=metadata if isinstance(metadata, dict) else {},
        compatibilidade=(str(meta["compatibility"]).strip() if meta.get("compatibility") else None),
        catalogo={k: v for k, v in catalogo.items() if not k.startswith("_")},
        arquivos=_listar_arquivos(pasta),
        ordem=catalogo.get("_ordem", 10_000),
    )
    skill.corpo = skill.reescrever_caminhos(corpo)
    return skill


def _listar_arquivos(pasta: Path) -> list[str]:
    arquivos: list[str] = []
    for caminho in sorted(pasta.rglob("*")):
        rel = caminho.relative_to(pasta)
        if any(parte in _IGNORAR for parte in rel.parts) or not caminho.is_file():
            continue
        if rel.as_posix() == "SKILL.md":
            continue
        arquivos.append(rel.as_posix())
        if len(arquivos) >= _MAX_ARQUIVOS_LISTADOS:
            break
    return arquivos


def _humanizar(sid: str) -> str:
    return " ".join(p.capitalize() for p in re.split(r"[-_]+", sid) if p)


def _primeira_frase(texto: str) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", texto)
    return (match.group(1) if match else texto)[:240]


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar textos em português."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()
