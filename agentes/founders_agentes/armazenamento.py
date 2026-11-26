"""Sessões, mensagens, perfil do negócio e consumo de tokens, em SQLite."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .provedores import Uso

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
    id TEXT PRIMARY KEY,
    dono TEXT NOT NULL,
    agente_atual TEXT,
    titulo TEXT,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessoes_dono ON sessoes (dono, atualizada_em);
CREATE TABLE IF NOT EXISTS mensagens (
    sessao_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    dados TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    PRIMARY KEY (sessao_id, seq)
);
CREATE TABLE IF NOT EXISTS perfis (
    dono TEXT PRIMARY KEY,
    dados TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consumo (
    sessao_id TEXT NOT NULL,
    modelo TEXT NOT NULL,
    entrada INTEGER NOT NULL DEFAULT 0,
    saida INTEGER NOT NULL DEFAULT 0,
    cache_leitura INTEGER NOT NULL DEFAULT 0,
    cache_escrita INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sessao_id, modelo)
);
"""
_ID_SESSAO = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
MAX_CAMPOS_PERFIL = 60


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Sessao:
    id: str
    dono: str
    agente_atual: str | None = None
    titulo: str | None = None
    mensagens: list[dict] = field(default_factory=list)
    persistente: bool = True
    sessao_pai: str | None = None  # para somar o consumo de consultas e conselhos na sessão de origem
    criada_em: str = ""

    @classmethod
    def efemera(cls, dono: str, agente: str | None = None, sessao_pai: str | None = None) -> "Sessao":
        return cls(id="tmp-" + uuid.uuid4().hex[:12], dono=dono, agente_atual=agente, persistente=False, sessao_pai=sessao_pai, criada_em=agora())


class Armazenamento:
    def __init__(self, banco: Path | str, pasta_arquivos: Path | str) -> None:
        self.pasta_arquivos = Path(pasta_arquivos)
        caminho = str(banco)
        if caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._trava = threading.RLock()
        with self._trava:
            if caminho != ":memory:":
                self._con.execute("PRAGMA journal_mode=WAL")
            self._con.executescript(_ESQUEMA)
            self._con.commit()

    # -- sessões ----------------------------------------------------------
    def criar_sessao(self, dono: str, agente: str | None = None, titulo: str | None = None, sessao_id: str | None = None) -> Sessao:
        if sessao_id is not None and not _ID_SESSAO.match(sessao_id):
            raise ValueError("id de sessão inválido: use de 6 a 64 letras, números, _ ou -")
        sessao = Sessao(id=sessao_id or uuid.uuid4().hex, dono=dono, agente_atual=agente, titulo=titulo, criada_em=agora())
        with self._trava:
            self._con.execute(
                "INSERT INTO sessoes (id, dono, agente_atual, titulo, criada_em, atualizada_em) VALUES (?, ?, ?, ?, ?, ?)",
                (sessao.id, dono, agente, titulo, sessao.criada_em, sessao.criada_em),
            )
            self._con.commit()
        return sessao

    def obter_sessao(self, sessao_id: str, dono: str) -> Sessao | None:
        with self._trava:
            linha = self._con.execute("SELECT * FROM sessoes WHERE id = ? AND dono = ?", (sessao_id, dono)).fetchone()
            if linha is None:
                return None
            mensagens = [
                json.loads(m["dados"])
                for m in self._con.execute("SELECT dados FROM mensagens WHERE sessao_id = ? ORDER BY seq", (sessao_id,))
            ]
        return Sessao(
            id=linha["id"], dono=linha["dono"], agente_atual=linha["agente_atual"], titulo=linha["titulo"],
            mensagens=mensagens, criada_em=linha["criada_em"],
        )

    def existe_sessao(self, sessao_id: str) -> bool:
        with self._trava:
            return self._con.execute("SELECT 1 FROM sessoes WHERE id = ?", (sessao_id,)).fetchone() is not None

    def listar_sessoes(self, dono: str, limite: int = 50) -> list[dict]:
        with self._trava:
            linhas = self._con.execute(
                "SELECT id, agente_atual, titulo, criada_em, atualizada_em FROM sessoes WHERE dono = ? ORDER BY atualizada_em DESC LIMIT ?",
                (dono, limite),
            ).fetchall()
        return [
            {"id": l["id"], "agenteAtual": l["agente_atual"], "titulo": l["titulo"], "criadaEm": l["criada_em"], "atualizadaEm": l["atualizada_em"]}
            for l in linhas
        ]

    def anexar(self, sessao: Sessao, mensagem: dict) -> None:
        sessao.mensagens.append(mensagem)
        if not sessao.persistente:
            return
        momento = agora()
        with self._trava:
            self._con.execute(
                "INSERT INTO mensagens (sessao_id, seq, dados, criada_em) VALUES (?, ?, ?, ?)",
                (sessao.id, len(sessao.mensagens) - 1, json.dumps(mensagem, ensure_ascii=False), momento),
            )
            self._con.execute("UPDATE sessoes SET atualizada_em = ? WHERE id = ?", (momento, sessao.id))
            self._con.commit()

    def definir_agente(self, sessao: Sessao, agente: str) -> None:
        sessao.agente_atual = agente
        if sessao.persistente:
            with self._trava:
                self._con.execute("UPDATE sessoes SET agente_atual = ?, atualizada_em = ? WHERE id = ?", (agente, agora(), sessao.id))
                self._con.commit()

    def definir_titulo(self, sessao: Sessao, titulo: str) -> None:
        sessao.titulo = titulo
        if sessao.persistente:
            with self._trava:
                self._con.execute("UPDATE sessoes SET titulo = ? WHERE id = ?", (titulo, sessao.id))
                self._con.commit()

    # -- consumo ----------------------------------------------------------
    def somar_consumo(self, sessao: Sessao, modelo: str, uso: Uso) -> None:
        alvo = sessao.id if sessao.persistente else sessao.sessao_pai
        if not alvo:
            return
        with self._trava:
            self._con.execute(
                """INSERT INTO consumo (sessao_id, modelo, entrada, saida, cache_leitura, cache_escrita) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (sessao_id, modelo) DO UPDATE SET
                     entrada = entrada + excluded.entrada, saida = saida + excluded.saida,
                     cache_leitura = cache_leitura + excluded.cache_leitura, cache_escrita = cache_escrita + excluded.cache_escrita""",
                (alvo, modelo, uso.entrada, uso.saida, uso.cache_leitura, uso.cache_escrita),
            )
            self._con.commit()

    def consumo(self, sessao_id: str) -> list[dict]:
        with self._trava:
            linhas = self._con.execute("SELECT * FROM consumo WHERE sessao_id = ? ORDER BY modelo", (sessao_id,)).fetchall()
        return [
            {"modelo": l["modelo"], "entrada": l["entrada"], "saida": l["saida"], "cacheLeitura": l["cache_leitura"], "cacheEscrita": l["cache_escrita"]}
            for l in linhas
        ]

    # -- perfil do negócio ------------------------------------------------
    def obter_perfil(self, dono: str) -> dict:
        with self._trava:
            linha = self._con.execute("SELECT dados FROM perfis WHERE dono = ?", (dono,)).fetchone()
        return json.loads(linha["dados"]) if linha else {}

    def atualizar_perfil(self, dono: str, campos: dict, substituir: bool = False) -> dict:
        with self._trava:
            perfil = {} if substituir else self.obter_perfil(dono)
            for chave, valor in campos.items():
                chave = str(chave).strip()[:80]
                if not chave:
                    continue
                if valor in (None, ""):
                    perfil.pop(chave, None)
                else:
                    perfil[chave] = str(valor).strip()[:500]
            if len(perfil) > MAX_CAMPOS_PERFIL:
                raise ValueError(f"o perfil aceita no máximo {MAX_CAMPOS_PERFIL} campos")
            self._con.execute(
                "INSERT INTO perfis (dono, dados, atualizado_em) VALUES (?, ?, ?) ON CONFLICT (dono) DO UPDATE SET dados = excluded.dados, atualizado_em = excluded.atualizado_em",
                (dono, json.dumps(perfil, ensure_ascii=False), agora()),
            )
            self._con.commit()
        return perfil

    # -- arquivos da sessão ----------------------------------------------
    def pasta_da_sessao(self, sessao: Sessao) -> Path | None:
        alvo = sessao.id if sessao.persistente else sessao.sessao_pai
        if not alvo:
            return None
        pasta = self.pasta_arquivos / alvo
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def caminho_arquivo(self, sessao_id: str, nome: str) -> Path | None:
        if not _ID_SESSAO.match(sessao_id) or "/" in nome or "\\" in nome or nome.startswith("."):
            return None
        caminho = self.pasta_arquivos / sessao_id / nome
        return caminho if caminho.is_file() else None

    def fechar(self) -> None:
        with self._trava:
            self._con.close()
