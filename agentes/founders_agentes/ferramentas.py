"""Ferramentas que os agentes podem chamar.

Elas dão às Skills o que o Claude oferece por baixo: ler os arquivos da skill sob
demanda, carregar outra skill, passar a conversa para outro agente, consultar um
especialista, lembrar o perfil do negócio, entregar arquivos e rodar os scripts
das skills.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .agentes import FERRAMENTAS_PADRAO, RECEPCAO, Agente, ErroAgente
from .armazenamento import Sessao
from .provedores import EspecFerramenta
from .skills import ErroSkill

if TYPE_CHECKING:
    from .orquestrador import Orquestrador

_NOME_ARQUIVO = re.compile(r"^[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ ._()-]{0,120}$")
_EXTENSOES_SALVAR = {".md", ".txt", ".csv", ".tsv", ".json", ".html", ".xml", ".yaml", ".yml"}
MAX_ARQUIVO = 2_000_000


@dataclass
class ContextoFerramenta:
    orquestrador: "Orquestrador"
    sessao: Sessao
    agente: Agente
    emitir: Callable[[str, dict], None]
    profundidade: int = 0


@dataclass
class ResultadoFerramenta:
    conteudo: str
    erro: bool = False
    passar_para: str | None = None
    arquivos: list[dict] = field(default_factory=list)


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict
    executar: Callable[[ContextoFerramenta, dict], ResultadoFerramenta]

    @property
    def espec(self) -> EspecFerramenta:
        return EspecFerramenta(self.nome, self.descricao, self.parametros)


def _objeto(propriedades: dict, obrigatorios: list[str]) -> dict:
    return {"type": "object", "properties": propriedades, "required": obrigatorios, "additionalProperties": False}


class CaixaFerramentas:
    def __init__(self, orquestrador: "Orquestrador") -> None:
        self.o = orquestrador

    def para_agente(self, agente: Agente, profundidade: int = 0) -> list[Ferramenta]:
        nomes = list(agente.ferramentas) if agente.ferramentas is not None else list(FERRAMENTAS_PADRAO)
        if profundidade > 0:
            nomes = [n for n in nomes if n not in ("passar_para_agente", "consultar_agente", "atualizar_perfil")]
        if not self.o.config.runtime.permitir_scripts or not any(
            self.o.biblioteca.obter(s).scripts for s in agente.skills if s in self.o.biblioteca
        ):
            nomes = [n for n in nomes if n != "executar_script"]
        if not agente.skills:
            nomes = [n for n in nomes if n not in ("ler_arquivo_skill", "listar_arquivos_skill", "executar_script")]
        ferramentas = []
        for nome in nomes:
            fabrica = getattr(self, f"_f_{nome}", None)
            if fabrica is None:
                continue
            ferramenta = fabrica(agente)
            if ferramenta is not None:
                ferramentas.append(ferramenta)
        return sorted(ferramentas, key=lambda f: f.nome)

    # -- definições -------------------------------------------------------
    def _f_ler_arquivo_skill(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "ler_arquivo_skill",
            "Lê um arquivo de uma skill (references/, scripts/, assets/). Chame sempre que as instruções da skill "
            "mandarem ler um arquivo, antes de responder sobre o assunto dele. Aceita caminho relativo à skill "
            "(ex.: references/guia.md) ou skill://<skill>/<caminho>.",
            _objeto(
                {
                    "caminho": {"type": "string", "description": "Caminho do arquivo, ex.: references/guia.md ou skill://outra-skill/references/x.md"},
                    "skill": {"type": "string", "description": "Id da skill dona do arquivo. Padrão: a skill principal deste agente."},
                },
                ["caminho"],
            ),
            self._ler_arquivo,
        )

    def _f_listar_arquivos_skill(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "listar_arquivos_skill",
            "Lista os arquivos de uma skill. Use quando precisar achar um arquivo de referência que não sabe o nome.",
            _objeto({"skill": {"type": "string", "description": "Id da skill. Padrão: a skill principal deste agente."}}, []),
            self._listar_arquivos,
        )

    def _f_carregar_skill(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "carregar_skill",
            "Carrega as instruções completas de outra skill. Chame quando o pedido do usuário cair no tema de uma "
            "skill de apoio (ou quando suas instruções mandarem rodar outra skill) e depois siga as instruções carregadas.",
            _objeto({"skill": {"type": "string", "description": "Id da skill a carregar."}}, ["skill"]),
            self._carregar_skill,
        )

    def _f_passar_para_agente(self, agente: Agente) -> Ferramenta | None:
        destinos = [a.id for a in self.o.registro.destinos_de_passagem(agente)]
        if not destinos:
            return None
        return Ferramenta(
            "passar_para_agente",
            "Passa a conversa para outro agente especialista, que responde ao usuário a partir daqui. Chame quando o "
            "pedido estiver fora da sua especialidade ou quando suas instruções mandarem passar a bola. No resumo, "
            "escreva tudo que o usuário já contou, para o próximo agente não perguntar de novo.",
            _objeto(
                {
                    "agente": {"type": "string", "enum": destinos, "description": "Id do agente que vai assumir."},
                    "motivo": {"type": "string", "description": "Por que este agente é o certo, em uma frase."},
                    "resumo": {"type": "string", "description": "O pedido do usuário e o contexto que ele já deu."},
                },
                ["agente", "resumo"],
            ),
            self._passar,
        )

    def _f_consultar_agente(self, agente: Agente) -> Ferramenta | None:
        destinos = [a.id for a in self.o.registro.destinos_de_passagem(agente) if a.id != RECEPCAO]
        if not destinos:
            return None
        return Ferramenta(
            "consultar_agente",
            "Pede a opinião de outro agente especialista sem sair da conversa: ele responde para você e você continua "
            "falando com o usuário. Use para uma segunda opinião ou para um número que é da área dele.",
            _objeto(
                {
                    "agente": {"type": "string", "enum": destinos, "description": "Id do agente consultado."},
                    "pergunta": {"type": "string", "description": "A pergunta, completa e objetiva."},
                    "contexto": {"type": "string", "description": "Dados do negócio que ele precisa para responder."},
                },
                ["agente", "pergunta"],
            ),
            self._consultar,
        )

    def _f_atualizar_perfil(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "atualizar_perfil",
            "Guarda fatos estáveis do negócio do usuário para todos os agentes (ex.: o que vende, faturamento mensal, "
            "tamanho do time, regime tributário, cidade, público). Chame assim que o usuário informar um desses fatos. "
            "Para apagar um campo, mande o valor vazio.",
            _objeto(
                {"campos": {"type": "object", "description": "Pares campo → valor, ex.: {\"faturamento_mensal\": \"R$ 80 mil\"}", "additionalProperties": {"type": "string"}}},
                ["campos"],
            ),
            self._atualizar_perfil,
        )

    def _f_salvar_arquivo(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "salvar_arquivo",
            "Salva um arquivo de entrega para o usuário baixar (.md, .txt, .csv, .json, .html). Use quando a entrega "
            "for longa, quando o usuário pedir um arquivo, ou para montar o JSON de entrada de um script.",
            _objeto(
                {
                    "nome": {"type": "string", "description": "Nome do arquivo com extensão, ex.: plano-de-acao.md"},
                    "conteudo": {"type": "string", "description": "Conteúdo completo do arquivo."},
                },
                ["nome", "conteudo"],
            ),
            self._salvar_arquivo,
        )

    def _f_executar_script(self, agente: Agente) -> Ferramenta:
        return Ferramenta(
            "executar_script",
            "Roda um script Python da pasta scripts/ de uma skill, dentro da pasta de arquivos da conversa (a mesma "
            "de salvar_arquivo). Use quando as instruções da skill mandarem rodar o script. Arquivos que o script "
            "criar ficam disponíveis para o usuário baixar.",
            _objeto(
                {
                    "skill": {"type": "string", "description": "Id da skill dona do script."},
                    "script": {"type": "string", "description": "Caminho do script na skill, ex.: scripts/gerar_plano_receita_xlsx.py"},
                    "argumentos": {"type": "array", "items": {"type": "string"}, "description": "Argumentos, ex.: [\"dados.json\", \"Plano.xlsx\"]"},
                },
                ["skill", "script"],
            ),
            self._executar_script,
        )

    # -- execução ---------------------------------------------------------
    def _skill_padrao(self, ctx: ContextoFerramenta, informada: str | None) -> str | None:
        return informada or ctx.agente.skill_principal or (ctx.agente.skills[0] if ctx.agente.skills else None)

    def _ler_arquivo(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        skill, rel = self.o.biblioteca.resolver(args["caminho"], self._skill_padrao(ctx, args.get("skill")))
        texto = skill.ler_texto(rel)
        return ResultadoFerramenta(f"# {skill.id}/{rel}\n\n{texto}")

    def _listar_arquivos(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        sid = self._skill_padrao(ctx, args.get("skill"))
        if not sid:
            return ResultadoFerramenta("informe a skill", erro=True)
        skill = self.o.biblioteca.obter(sid)
        if not skill.arquivos:
            return ResultadoFerramenta(f"A skill {sid} não tem arquivos além do SKILL.md.")
        return ResultadoFerramenta(f"Arquivos da skill {sid}:\n" + "\n".join(f"- {a}" for a in skill.arquivos))

    def _carregar_skill(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        skill = self.o.biblioteca.obter(args["skill"])
        arquivos = ("\n\nArquivos desta skill: " + ", ".join(skill.arquivos[:60])) if skill.arquivos else ""
        return ResultadoFerramenta(f'<skill id="{skill.id}">\n{skill.corpo.strip()}\n</skill>{arquivos}')

    def _passar(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        destino = self.o.registro.obter_disponivel(args["agente"])
        if destino.id == ctx.agente.id:
            return ResultadoFerramenta("Você já é esse agente: continue respondendo.", erro=True)
        motivo = (args.get("motivo") or "").strip()
        texto = f"Conversa passada de {ctx.agente.nome} para {destino.nome} ({destino.id})."
        if motivo:
            texto += f" Motivo: {motivo}"
        texto += f"\nResumo do que o usuário já contou: {args['resumo'].strip()}\nA partir daqui, {destino.nome} responde ao usuário."
        return ResultadoFerramenta(texto, passar_para=destino.id)

    def _consultar(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        if ctx.profundidade > 0:
            return ResultadoFerramenta("Consultas dentro de consultas não são permitidas.", erro=True)
        resposta = self.o.consultar(ctx, args["agente"], args["pergunta"], args.get("contexto") or "")
        destino = self.o.registro.obter(args["agente"])
        return ResultadoFerramenta(f"Resposta de {destino.nome}:\n\n{resposta}")

    def _atualizar_perfil(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        campos = args["campos"]
        if not isinstance(campos, dict) or not campos:
            return ResultadoFerramenta("mande pelo menos um campo", erro=True)
        perfil = self.o.armazenamento.atualizar_perfil(ctx.sessao.dono, campos)
        ctx.emitir("perfil", {"perfil": perfil})
        return ResultadoFerramenta("Perfil atualizado: " + "; ".join(f"{k}: {v}" for k, v in sorted(perfil.items())))

    def _salvar_arquivo(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        pasta = self.o.armazenamento.pasta_da_sessao(ctx.sessao)
        if pasta is None:
            return ResultadoFerramenta("Esta conversa não guarda arquivos: entregue o conteúdo no chat.", erro=True)
        nome = args["nome"].strip()
        extensao = os.path.splitext(nome)[1].lower()
        if not _NOME_ARQUIVO.match(nome) or extensao not in _EXTENSOES_SALVAR:
            return ResultadoFerramenta(f"nome de arquivo inválido; use letras, números e uma destas extensões: {', '.join(sorted(_EXTENSOES_SALVAR))}", erro=True)
        dados = args["conteudo"].encode("utf-8")
        if len(dados) > MAX_ARQUIVO:
            return ResultadoFerramenta("arquivo grande demais (máximo 2 MB)", erro=True)
        (pasta / nome).write_bytes(dados)
        arquivo = self._descrever(ctx, nome, len(dados))
        ctx.emitir("arquivo", arquivo)
        return ResultadoFerramenta(f"Arquivo salvo: {nome} ({len(dados)} bytes). O usuário baixa em {arquivo['url']}.", arquivos=[arquivo])

    def _executar_script(self, ctx: ContextoFerramenta, args: dict) -> ResultadoFerramenta:
        if not self.o.config.runtime.permitir_scripts:
            return ResultadoFerramenta("A execução de scripts está desligada nesta instalação.", erro=True)
        skill = self.o.biblioteca.obter(args["skill"])
        rel = args["script"].strip().lstrip("./")
        if not rel.startswith("scripts/") or not rel.endswith(".py"):
            return ResultadoFerramenta("só dá para rodar arquivos .py da pasta scripts/ da skill", erro=True)
        caminho = skill.caminho(rel)
        if not caminho.is_file():
            return ResultadoFerramenta(f"script não encontrado: {rel}", erro=True)
        argumentos = [str(a) for a in args.get("argumentos") or []]
        for arg in argumentos:
            if arg.startswith(("/", "~")) or ".." in arg.replace("\\", "/").split("/"):
                return ResultadoFerramenta(f"argumento não permitido (fora da pasta da conversa): {arg}", erro=True)
        pasta = self.o.armazenamento.pasta_da_sessao(ctx.sessao)
        if pasta is None:
            return ResultadoFerramenta("Esta conversa não guarda arquivos: não dá para rodar scripts aqui.", erro=True)
        antes = {p.name: p.stat().st_mtime for p in pasta.iterdir() if p.is_file()}
        inicio = time.time()
        ambiente = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(pasta), "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
        try:
            processo = subprocess.run(
                [sys.executable, "-I", str(caminho), *argumentos],
                cwd=pasta, env=ambiente, capture_output=True, text=True,
                timeout=self.o.config.runtime.timeout_script,
            )
        except subprocess.TimeoutExpired:
            return ResultadoFerramenta(f"o script passou de {self.o.config.runtime.timeout_script} s e foi interrompido", erro=True)
        novos = []
        for p in sorted(pasta.iterdir()):
            if p.is_file() and (p.name not in antes or p.stat().st_mtime > antes[p.name]) and p.stat().st_mtime >= inicio - 1:
                arquivo = self._descrever(ctx, p.name, p.stat().st_size)
                novos.append(arquivo)
                ctx.emitir("arquivo", arquivo)
        saida = _cauda(processo.stdout, 6000)
        erros = _cauda(processo.stderr, 3000)
        texto = f"Código de saída: {processo.returncode}\n\nSaída:\n{saida or '(vazia)'}"
        if erros:
            texto += f"\n\nErros:\n{erros}"
        if novos:
            texto += "\n\nArquivos criados: " + ", ".join(f"{a['nome']} ({a['url']})" for a in novos)
        return ResultadoFerramenta(texto, erro=processo.returncode != 0, arquivos=novos)

    def _descrever(self, ctx: ContextoFerramenta, nome: str, tamanho: int) -> dict:
        sessao_id = ctx.sessao.id if ctx.sessao.persistente else ctx.sessao.sessao_pai
        return {"nome": nome, "tamanho": tamanho, "url": f"/v1/sessoes/{sessao_id}/arquivos/{nome}"}

    # -- validação e despacho --------------------------------------------
    def executar(self, ferramentas: list[Ferramenta], ctx: ContextoFerramenta, nome: str, args: dict | None, erro_args: str | None) -> ResultadoFerramenta:
        ferramenta = next((f for f in ferramentas if f.nome == nome), None)
        if ferramenta is None:
            return ResultadoFerramenta(f"ferramenta desconhecida: {nome}", erro=True)
        if erro_args or args is None:
            return ResultadoFerramenta(f"INVALID_JSON: {erro_args or 'argumentos ausentes'}. Refaça a chamada com um objeto JSON válido.", erro=True)
        problema = validar(ferramenta.parametros, args)
        if problema:
            return ResultadoFerramenta(f"argumentos inválidos: {problema}. Refaça a chamada.", erro=True)
        try:
            resultado = ferramenta.executar(ctx, args)
        except (ErroSkill, ErroAgente, ValueError, OSError) as exc:
            return ResultadoFerramenta(str(exc), erro=True)
        limite = self.o.config.runtime.max_caracteres_ferramenta
        if len(resultado.conteudo) > limite:
            resultado.conteudo = resultado.conteudo[:limite] + f"\n\n[... resultado cortado em {limite} caracteres]"
        return resultado


def validar(esquema: dict, valor, caminho: str = "") -> str | None:
    """Validação mínima de JSON Schema (tipo, obrigatórios, enum, propriedades extras)."""
    tipo = esquema.get("type")
    rotulo = caminho or "argumentos"
    tipos = {"object": dict, "array": list, "string": str, "boolean": bool}
    if tipo in tipos and not isinstance(valor, tipos[tipo]):
        return f"{rotulo} deveria ser {tipo}"
    if tipo == "integer" and (not isinstance(valor, int) or isinstance(valor, bool)):
        return f"{rotulo} deveria ser inteiro"
    if tipo == "number" and (not isinstance(valor, (int, float)) or isinstance(valor, bool)):
        return f"{rotulo} deveria ser número"
    if "enum" in esquema and valor not in esquema["enum"]:
        return f"{rotulo} tem valor fora da lista permitida"
    if tipo == "object":
        props = esquema.get("properties", {})
        for chave in esquema.get("required", []):
            if chave not in valor:
                return f"falta o campo {chave}"
        extras = esquema.get("additionalProperties", True)
        for chave, item in valor.items():
            if chave in props:
                problema = validar(props[chave], item, f"{caminho}.{chave}" if caminho else chave)
            elif extras is False:
                problema = f"campo não esperado: {chave}"
            elif isinstance(extras, dict):
                problema = validar(extras, item, f"{caminho}.{chave}" if caminho else chave)
            else:
                problema = None
            if problema:
                return problema
    if tipo == "array" and "items" in esquema:
        for i, item in enumerate(valor):
            problema = validar(esquema["items"], item, f"{rotulo}[{i}]")
            if problema:
                return problema
    return None


def _cauda(texto: str, limite: int) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else "[...]\n" + texto[-limite:]
