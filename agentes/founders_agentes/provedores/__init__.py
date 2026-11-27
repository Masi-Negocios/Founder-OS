"""Central de provedores: resolve "provedor:modelo" para o cliente certo."""
from __future__ import annotations

import importlib.util
import threading

from ..config import Config
from .base import (
    BlocoSistema,
    ChamadaFerramenta,
    EspecFerramenta,
    ErroProvedor,
    OpcoesChamada,
    Provedor,
    RespostaModelo,
    Uso,
)

__all__ = [
    "BlocoSistema", "ChamadaFerramenta", "EspecFerramenta", "ErroProvedor", "OpcoesChamada",
    "Provedor", "RespostaModelo", "Uso", "CentralProvedores",
]


class CentralProvedores:
    def __init__(self, config: Config, extras: dict[str, Provedor] | None = None) -> None:
        self.config = config
        self._extras = dict(extras or {})
        self._cache: dict[str, Provedor] = {}
        self._trava = threading.Lock()

    def separar(self, referencia: str) -> tuple[str, str]:
        ref = self.config.apelidos.get(referencia, referencia)
        nome, sep, modelo = ref.partition(":")
        if not sep or not nome or not modelo:
            raise ErroProvedor(f"modelo '{referencia}' sem provedor: use provedor:modelo (ex.: anthropic:claude-opus-5-5)")
        return nome, modelo

    def obter(self, nome: str) -> Provedor:
        if nome in self._extras:
            return self._extras[nome]
        with self._trava:
            if nome in self._cache:
                return self._cache[nome]
            cfg = self.config.provedores.get(nome)
            if cfg is None:
                raise ErroProvedor(f"provedor desconhecido: {nome}")
            opcoes = cfg.opcoes
            if cfg.tipo == "anthropic":
                from .claude import ProvedorClaude

                provedor = ProvedorClaude(
                    nome,
                    chave=cfg.chave,
                    base_url=cfg.base_url,
                    fallbacks=opcoes.get("fallbacks", "default") or None,
                    max_tokens=int(opcoes.get("max_tokens", 64_000)),
                    cache_ttl=opcoes.get("cache_ttl"),
                )
            elif cfg.tipo == "openai_compat":
                from .openai_compat import ProvedorOpenAICompat

                if not cfg.base_url:
                    raise ErroProvedor(f"provedor {nome} sem base_url")
                provedor = ProvedorOpenAICompat(
                    nome,
                    base_url=cfg.base_url,
                    chave=cfg.chave,
                    cabecalhos=cfg.cabecalhos,
                    timeout=float(opcoes.get("timeout", 300)),
                    max_tokens=opcoes.get("max_tokens"),
                    enviar_esforco=bool(opcoes.get("enviar_esforco", False)),
                    uso_no_stream=bool(opcoes.get("uso_no_stream", True)),
                    max_mensagens=int(opcoes.get("max_mensagens", 0)),
                )
            elif cfg.tipo == "demo":
                from .demo import ProvedorDemo

                provedor = ProvedorDemo(nome, pausa=float(opcoes.get("pausa", 0.01)))
            else:
                raise ErroProvedor(f"tipo de provedor desconhecido: {cfg.tipo}")
            self._cache[nome] = provedor
            return provedor

    def resolver(self, referencia: str) -> tuple[Provedor, str]:
        nome, modelo = self.separar(referencia)
        return self.obter(nome), modelo

    def situacao(self) -> list[dict]:
        linhas = []
        for nome, cfg in sorted(self.config.provedores.items()):
            item = {"nome": nome, "tipo": cfg.tipo, "baseUrl": cfg.base_url, "chaveEnv": cfg.chave_env}
            if cfg.tipo == "anthropic":
                item["sdkInstalado"] = importlib.util.find_spec("anthropic") is not None
                item["chaveDefinida"] = bool(cfg.chave)
                item["pronto"] = item["sdkInstalado"]
            elif cfg.tipo == "openai_compat":
                item["chaveDefinida"] = bool(cfg.chave)
                item["pronto"] = bool(cfg.chave) or not cfg.chave_env
            else:
                item["pronto"] = True
            linhas.append(item)
        return linhas
