"""Instala skills e perfis de agente em um projeto. Requer Python 3.8+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


RAIZ = Path(__file__).resolve().parents[1]
SKILLS = RAIZ / "plugins/founders-os/skills"
REGISTRO = ".agents/founders-os.json"
ID = r"[a-z0-9]+(?:-[a-z0-9]+)*"


def catalogo():
    itens = json.loads((RAIZ / "catalogo.json").read_text(encoding="utf-8"))["skills"]
    itens = [*itens, {"id": "boas-vindas", "nome": "Boas-vindas"}]
    return {s["id"]: s for s in itens}


def selecionar(itens, pedidos):
    desconhecidos = set(pedidos) - itens.keys()
    if desconhecidos:
        raise ValueError("Skill desconhecida: " + ", ".join(sorted(desconhecidos)) + ". Consulte --listar.")
    grupos = {itens[i]["grupo"] for i in pedidos if "grupo" in itens[i]}
    return [s for s in itens.values() if not pedidos or s["id"] in pedidos or s.get("grupo") in grupos]


def perfil(skill, ambiente):
    nome = skill["agente"]
    pasta = ".agents/skills/" + skill["id"]
    texto = (f"Use a skill {skill['id']} para conduzir o trabalho de {skill['nome']}. "
             f"Leia {pasta}/SKILL.md na raiz deste projeto e consulte as referências relativas à "
             "pasta da skill conforme o método pedir. Use os dados e as ferramentas disponíveis "
             "nesta sessão. Quando faltarem informações do negócio, devolva as perguntas ao solicitante.")
    descricao = json.dumps(skill["paraQue"], ensure_ascii=False)
    if ambiente == "codex":
        corpo = f'name = "{nome}"\ndescription = {descricao}\ndeveloper_instructions = {json.dumps(texto, ensure_ascii=False)}\n'
        return f".codex/agents/{nome}.toml", corpo.encode("utf-8")
    corpo = f"---\ndescription: {descricao}\nmode: subagent\n---\n\n{texto}\n"
    return f".opencode/agents/{nome}.md", corpo.encode("utf-8")


def preparar(skills, ambiente):
    def falha_de_leitura(erro):
        raise erro

    arquivos = {}
    for skill in skills:
        pasta = SKILLS / skill["id"]
        if not (pasta / "SKILL.md").is_file():
            raise ValueError(f"Skill incompleta no pacote: {pasta}")
        for base, diretorios, nomes in os.walk(pasta, onerror=falha_de_leitura):
            diretorios[:] = [d for d in diretorios if d not in {".git", ".venv", "__pycache__", "node_modules"}]
            for nome in nomes:
                if nome == ".DS_Store" or nome.endswith(".pyc"):
                    continue
                origem = Path(base) / nome
                if origem.is_symlink() or not origem.is_file():
                    raise ValueError(f"Recurso da skill precisa ser um arquivo regular: {origem}")
                relativo = origem.relative_to(SKILLS).as_posix()
                arquivos[f".agents/skills/{relativo}"] = origem.read_bytes()
        if "agente" in skill:
            caminho, dados = perfil(skill, ambiente)
            arquivos[caminho] = dados
    return arquivos


def soma(dados):
    return hashlib.sha256(dados).hexdigest()


def gravar(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=caminho.parent) as pasta:
        temporario = Path(pasta) / "novo"
        temporario.write_bytes(dados)
        os.replace(temporario, caminho)


def destino(projeto, relativo):
    partes = relativo.split("/")
    if any(p in {"", ".", ".."} or "\\" in p or ":" in p for p in partes):
        raise ValueError(f"Caminho inválido no registro: {relativo}")
    skill = partes[:2] == [".agents", "skills"] and len(partes) >= 4 and re.fullmatch(ID, partes[2])
    agente = re.fullmatch(r"\.codex/agents/masi-[a-z0-9-]+\.toml|\.opencode/agents/masi-[a-z0-9-]+\.md", relativo)
    if not (skill or agente):
        raise ValueError(f"Caminho fora da instalação: {relativo}")
    caminho = projeto
    for indice, parte in enumerate(partes):
        caminho = caminho / parte
        if caminho.is_symlink() or caminho.resolve() != caminho:
            raise ValueError(f"O destino contém um link: {caminho}")
        if indice < len(partes) - 1 and caminho.exists() and not caminho.is_dir():
            raise ValueError(f"O destino requer uma pasta, mas existe um arquivo: {caminho}")
    return caminho


def sincronizar(projeto, arquivos, gerencia):
    registro = projeto / REGISTRO
    if registro.is_symlink():
        raise ValueError(f"O registro é um link: {registro}")
    estado = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    if not isinstance(estado, dict) or estado.keys() - {"arquivos", "pendentes"}:
        raise ValueError(f"Registro de instalação inválido: {registro}")
    for mapa in estado.values():
        if not isinstance(mapa, dict) or any(
            not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in mapa.values()
        ):
            raise ValueError(f"Assinaturas inválidas no registro de instalação: {registro}")
    anteriores = estado.get("arquivos", {})
    # Uma execução interrompida pode ter concluído apenas algumas substituições atômicas.
    for relativo, esperado in estado.get("pendentes", {}).items():
        caminho = destino(projeto, relativo)
        if caminho.is_file() and soma(caminho.read_bytes()) == esperado:
            anteriores[relativo] = esperado

    desejados = {p: soma(dados) for p, dados in arquivos.items()}
    obsoletos = {p for p in anteriores if gerencia(p) and p not in desejados}
    escrever, apagar = {}, []
    for relativo in sorted(desejados.keys() | obsoletos):
        caminho = destino(projeto, relativo)
        anterior = anteriores.get(relativo)
        if caminho.exists() and (not caminho.is_file() or anterior is None):
            raise ValueError(f"Já existe um arquivo ou pasta de outra instalação: {caminho}")
        atual = soma(caminho.read_bytes()) if caminho.is_file() else None
        if atual is not None and atual != anterior and atual != desejados.get(relativo):
            raise ValueError(f"Arquivo editado no projeto: {caminho}. Guarde a sua edição antes de continuar.")
        if relativo in obsoletos:
            if atual:
                apagar.append(caminho)
        elif atual != desejados[relativo]:
            escrever[relativo] = desejados[relativo]

    def salvar(valores):
        gravar(registro, (json.dumps(valores, indent=2, sort_keys=True) + "\n").encode())

    finais = {p: h for p, h in anteriores.items() if p not in obsoletos}
    finais.update(desejados)
    if escrever:
        salvar({"arquivos": anteriores, "pendentes": escrever})
    for relativo in escrever:
        gravar(projeto / relativo, arquivos[relativo])
    for caminho in apagar:
        caminho.unlink()
    for pasta in sorted({(projeto / r).parent for r in obsoletos}, reverse=True):
        while pasta != projeto and pasta.is_dir() and not any(pasta.iterdir()):
            pasta.rmdir()
            pasta = pasta.parent
    if finais:
        if estado != {"arquivos": finais} or escrever:
            salvar({"arquivos": finais})
    else:
        registro.unlink(missing_ok=True)
    return len(escrever), len(apagar)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    acao = parser.add_mutually_exclusive_group()
    acao.add_argument("--listar", action="store_true", help="listar IDs de skills e perfis de agente")
    acao.add_argument("--remover", action="store_true", help="remover toda a instalação gerenciada do projeto")
    parser.add_argument("--projeto", type=Path, default=Path.cwd(), help="pasta do projeto (padrão: pasta atual)")
    parser.add_argument("--ambiente", choices=["codex", "opencode"], default="codex", help="formato dos agentes (padrão: codex)")
    parser.add_argument("--skill", action="append", default=[], metavar="ID", help="selecionar uma skill (repetível)")
    args = parser.parse_args()
    itens = catalogo()
    if args.listar:
        for s in itens.values():
            agente = f" [agente: {s['agente']}]" if "agente" in s else ""
            print(f"{s['id']}  {s['nome']}{agente}")
        return
    if args.remover and args.skill:
        parser.error("--remover remove a instalação inteira. Use sem --skill.")
    projeto = args.projeto.expanduser().resolve()
    if not projeto.is_dir():
        raise ValueError(f"Pasta de projeto inexistente: {projeto}")
    selecao = selecionar(itens, args.skill)
    arquivos = {} if args.remover else preparar(selecao, args.ambiente)
    ids = {s["id"] for s in selecao}

    def gerencia(relativo):
        if args.remover:
            return True
        if relativo.startswith(".agents/skills/"):
            return not args.skill or relativo.split("/")[2] in ids
        return not args.skill and relativo.startswith(f".{args.ambiente}/agents/")

    base = projeto / ".agents"
    if base.is_symlink() or base.resolve() != base:
        raise ValueError(f"A pasta de instalação é um link: {base}")
    if args.remover and not (projeto / REGISTRO).exists():
        print("Nenhuma instalação registrada neste projeto.")
        return
    base.mkdir(exist_ok=True)
    trava = base / ".founders-os.lock"
    try:
        trava.mkdir()
    except FileExistsError:
        raise ValueError(f"Instalação em andamento. Se foi interrompida, remova a pasta vazia {trava} e repita.")
    try:
        escritos, removidos = sincronizar(projeto, arquivos, gerencia)
    finally:
        trava.rmdir()
    if args.remover:
        print(f"Instalação removida de {projeto} ({removidos} arquivos).")
    else:
        agentes = sum("agente" in s for s in selecao)
        print(f"{projeto}: {len(selecao)} skills e {agentes} perfis para {args.ambiente}. "
              f"{escritos} arquivos gravados, {removidos} removidos.")
        primeira = "boas-vindas" if "boas-vindas" in ids else selecao[0]["id"]
        print(f"Abra o projeto em {args.ambiente} e peça para usar a skill {primeira}.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as erro:
        sys.exit(f"Founders OS: {erro}")
