"""Configuração: arquivo TOML + variáveis de ambiente.

Valores de texto aceitam ${VAR} e ${VAR:-padrão}. Caminhos relativos são
resolvidos a partir da pasta do arquivo de configuração.
"""
from __future__ import annotations

import hashlib
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .skills import FonteSkills

MODELO_PADRAO = "anthropic:claude-opus-5-5"
PASTA_PACOTE = Path(__file__).resolve().parent
CONFIG_EMBUTIDA = PASTA_PACOTE.parent / "config.toml"

# Provedores prontos: basta definir a chave no ambiente. "openai_compat" cobre
# qualquer API no formato Chat Completions da OpenAI.
PROVEDORES_PADRAO: dict[str, dict] = {
    "anthropic": {"tipo": "anthropic", "chave_env": "ANTHROPIC_API_KEY"},
    "openai": {"tipo": "openai_compat", "base_url": "https://api.openai.com/v1", "chave_env": "OPENAI_API_KEY"},
    "openrouter": {"tipo": "openai_compat", "base_url": "https://openrouter.ai/api/v1", "chave_env": "OPENROUTER_API_KEY"},
    "gemini": {"tipo": "openai_compat", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "chave_env": "GEMINI_API_KEY"},
    "groq": {"tipo": "openai_compat", "base_url": "https://api.groq.com/openai/v1", "chave_env": "GROQ_API_KEY"},
    "deepseek": {"tipo": "openai_compat", "base_url": "https://api.deepseek.com/v1", "chave_env": "DEEPSEEK_API_KEY"},
    "mistral": {"tipo": "openai_compat", "base_url": "https://api.mistral.ai/v1", "chave_env": "MISTRAL_API_KEY"},
    "xai": {"tipo": "openai_compat", "base_url": "https://api.x.ai/v1", "chave_env": "XAI_API_KEY"},
    "together": {"tipo": "openai_compat", "base_url": "https://api.together.xyz/v1", "chave_env": "TOGETHER_API_KEY"},
    "ollama": {"tipo": "openai_compat", "base_url": "${OLLAMA_BASE_URL:-http://localhost:11434/v1}", "chave_env": ""},
    "demo": {"tipo": "demo"},
}

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


class ErroConfig(ValueError):
    pass


def expandir_variaveis(valor):
    if isinstance(valor, str):
        return _VAR.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), valor)
    if isinstance(valor, list):
        return [expandir_variaveis(v) for v in valor]
    if isinstance(valor, dict):
        return {k: expandir_variaveis(v) for k, v in valor.items()}
    return valor


@dataclass
class ConfigProvedor:
    nome: str
    tipo: str
    base_url: str | None = None
    chave_env: str | None = None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    opcoes: dict = field(default_factory=dict)

    @property
    def chave(self) -> str | None:
        return os.environ.get(self.chave_env) if self.chave_env else None


@dataclass
class ConfigRuntime:
    max_turnos: int = 12
    max_passagens: int = 3
    permitir_scripts: bool = False
    timeout_script: int = 120
    max_caracteres_ferramenta: int = 60_000
    banco: Path = Path("dados/agentes.db")
    pasta_arquivos: Path = Path("dados/arquivos")


@dataclass
class ConfigServidor:
    host: str = "127.0.0.1"
    porta: int = 8787
    chaves_api: dict[str, str] = field(default_factory=dict)  # chave -> dono
    cors: str = ""
    eventos_no_openai: bool = True


@dataclass
class Config:
    arquivo: Path | None = None
    fontes_skills: list[FonteSkills] = field(default_factory=list)
    excluir_skills: list[str] = field(default_factory=list)
    agentes_automaticos: bool = True
    permitir_so_claude_code: bool = False
    modelo_padrao: str = MODELO_PADRAO
    modelos_reserva: list[str] = field(default_factory=list)
    apelidos: dict[str, str] = field(default_factory=dict)
    esforco_padrao: str | None = None
    provedores: dict[str, ConfigProvedor] = field(default_factory=dict)
    agentes: list[dict] = field(default_factory=list)
    times: list[dict] = field(default_factory=list)
    runtime: ConfigRuntime = field(default_factory=ConfigRuntime)
    servidor: ConfigServidor = field(default_factory=ConfigServidor)


def carregar_config(caminho: str | os.PathLike | None = None) -> Config:
    """Lê a configuração. Sem caminho, usa FOUNDERS_AGENTES_CONFIG ou o config.toml do pacote."""
    caminho = caminho or os.environ.get("FOUNDERS_AGENTES_CONFIG") or (CONFIG_EMBUTIDA if CONFIG_EMBUTIDA.is_file() else None)
    dados: dict = {}
    base = Path.cwd()
    arquivo = None
    if caminho:
        arquivo = Path(caminho).expanduser().resolve()
        try:
            with arquivo.open("rb") as fp:
                dados = tomllib.load(fp)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ErroConfig(f"não consegui ler {arquivo}: {exc}") from exc
        base = arquivo.parent
    dados = expandir_variaveis(dados)

    def caminho_de(valor: str | None) -> Path | None:
        if not valor:
            return None
        p = Path(valor).expanduser()
        return p if p.is_absolute() else (base / p).resolve()

    sec_skills = dados.get("skills", {})
    excluir = [str(s) for s in sec_skills.get("excluir", [])]
    fontes: list[FonteSkills] = []
    for item in sec_skills.get("fontes", []):
        if isinstance(item, str):
            item = {"caminho": item}
        fontes.append(FonteSkills(
            caminho=caminho_de(item["caminho"]),
            catalogo=caminho_de(item.get("catalogo")),
            rotulo=item.get("rotulo"),
            excluir=tuple(excluir) + tuple(item.get("excluir", [])),
        ))
    for extra in filter(None, os.environ.get("FOUNDERS_AGENTES_SKILLS", "").split(os.pathsep)):
        fontes.append(FonteSkills(caminho=Path(extra).expanduser().resolve(), excluir=tuple(excluir)))

    sec_modelos = dados.get("modelos", {})
    modelo_padrao = os.environ.get("FOUNDERS_AGENTES_MODELO") or sec_modelos.get("padrao") or MODELO_PADRAO
    reserva_env = os.environ.get("FOUNDERS_AGENTES_RESERVA")
    reserva = [m.strip() for m in reserva_env.split(",") if m.strip()] if reserva_env else list(sec_modelos.get("reserva", []))

    provedores: dict[str, ConfigProvedor] = {}
    sec_provedores = dados.get("provedores", {})
    for nome in {**PROVEDORES_PADRAO, **sec_provedores}:
        bruto = {**expandir_variaveis(PROVEDORES_PADRAO.get(nome, {})), **sec_provedores.get(nome, {})}
        if "tipo" not in bruto:
            raise ErroConfig(f"provedor '{nome}' sem 'tipo' (anthropic, openai_compat ou demo)")
        conhecidas = {"tipo", "base_url", "chave_env", "cabecalhos"}
        provedores[nome] = ConfigProvedor(
            nome=nome,
            tipo=bruto["tipo"],
            base_url=(bruto.get("base_url") or None),
            chave_env=(bruto.get("chave_env") or None),
            cabecalhos=dict(bruto.get("cabecalhos", {})),
            opcoes={k: v for k, v in bruto.items() if k not in conhecidas},
        )

    sec_runtime = dados.get("runtime", {})
    pasta_dados = os.environ.get("FOUNDERS_AGENTES_DADOS")
    runtime = ConfigRuntime(
        max_turnos=int(sec_runtime.get("max_turnos", 12)),
        max_passagens=int(sec_runtime.get("max_passagens", 3)),
        permitir_scripts=_booleano(os.environ.get("FOUNDERS_AGENTES_SCRIPTS"), sec_runtime.get("permitir_scripts", False)),
        timeout_script=int(sec_runtime.get("timeout_script", 120)),
        max_caracteres_ferramenta=int(sec_runtime.get("max_caracteres_ferramenta", 60_000)),
        banco=(Path(pasta_dados) / "agentes.db") if pasta_dados else (caminho_de(sec_runtime.get("banco")) or Path("dados/agentes.db").resolve()),
        pasta_arquivos=(Path(pasta_dados) / "arquivos") if pasta_dados else (caminho_de(sec_runtime.get("pasta_arquivos")) or Path("dados/arquivos").resolve()),
    )

    sec_servidor = dados.get("servidor", {})
    servidor = ConfigServidor(
        host=os.environ.get("FOUNDERS_AGENTES_HOST") or sec_servidor.get("host", "127.0.0.1"),
        porta=int(os.environ.get("FOUNDERS_AGENTES_PORTA") or sec_servidor.get("porta", 8787)),
        chaves_api=ler_chaves_api(os.environ.get(sec_servidor.get("chaves_api_env", "FOUNDERS_AGENTES_CHAVES"), "")),
        cors=sec_servidor.get("cors", ""),
        eventos_no_openai=bool(sec_servidor.get("eventos_no_openai", True)),
    )

    return Config(
        arquivo=arquivo,
        fontes_skills=fontes,
        excluir_skills=excluir,
        agentes_automaticos=bool(sec_skills.get("agentes_automaticos", True)),
        permitir_so_claude_code=bool(sec_skills.get("permitir_so_claude_code", False)),
        modelo_padrao=modelo_padrao,
        modelos_reserva=reserva,
        apelidos=dict(sec_modelos.get("apelidos", {})),
        esforco_padrao=sec_modelos.get("esforco") or None,
        provedores=provedores,
        agentes=list(dados.get("agentes", [])),
        times=list(dados.get("times", [])),
        runtime=runtime,
        servidor=servidor,
    )


def ler_chaves_api(texto: str) -> dict[str, str]:
    """"chave1:empresa-a,chave2" -> {chave1: empresa-a, chave2: chave-<hash>}."""
    chaves: dict[str, str] = {}
    for parte in filter(None, (p.strip() for p in texto.split(","))):
        chave, _, dono = parte.partition(":")
        chave = chave.strip()
        if chave:
            chaves[chave] = dono.strip() or "chave-" + hashlib.sha256(chave.encode()).hexdigest()[:10]
    return chaves


def _booleano(env: str | None, padrao) -> bool:
    if env is None or env == "":
        return bool(padrao)
    return env.strip().lower() in ("1", "true", "sim", "yes", "on")
