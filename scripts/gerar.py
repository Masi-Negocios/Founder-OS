"""Gera as boas-vindas, o catálogo do site e o manifesto portátil do plugin.
Uso: python3 scripts/gerar.py   (na raiz do repositório)"""
import json, os, sys
import re
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat = json.load(open(os.path.join(RAIZ, "catalogo.json"), encoding="utf-8"))
pasta_skills = os.path.join(RAIZ, "plugins", "founders-os", "skills")

# Toda skill do catálogo tem que existir no plugin, e vice-versa: o catálogo não pode mentir.
no_plugin = {d for d in os.listdir(pasta_skills) if os.path.isfile(os.path.join(pasta_skills, d, "SKILL.md"))} - {"boas-vindas"}
no_catalogo = {s["id"] for s in cat["skills"]}
if len(no_catalogo) != len(cat["skills"]):
    sys.exit("ID de skill repetido no catálogo.")
agentes = [s["agente"] for s in cat["skills"] if "agente" in s]
if len(agentes) != len(set(agentes)) or any(not re.fullmatch(r"masi-[a-z0-9]+(?:-[a-z0-9]+)*", a) for a in agentes):
    sys.exit("Cada agente precisa de um identificador único no formato masi-nome.")
if no_plugin != no_catalogo:
    sys.exit(f"Catálogo e plugin divergem. Só no plugin: {sorted(no_plugin - no_catalogo)}. Só no catálogo: {sorted(no_catalogo - no_plugin)}")
areas_invalidas = [s["id"] for s in cat["skills"] if s["area"] not in cat["areas"]]
if areas_invalidas:
    sys.exit(f"Área fora da lista em: {areas_invalidas}")

# Material compartilhado (ex.: o guia de voz da Masi) mora uma vez em compartilhado/ e é copiado
# para dentro de cada skill que o declara em "referencias": a skill instalada precisa ter o arquivo.
import shutil
for s in cat["skills"]:
    for ref in s.get("referencias", []):
        origem = os.path.join(RAIZ, "compartilhado", ref)
        if not os.path.isfile(origem):
            sys.exit(f"{s['id']}: referência compartilhada inexistente: {ref}")
        destino = os.path.join(pasta_skills, s["id"], "references")
        os.makedirs(destino, exist_ok=True)
        shutil.copyfile(origem, os.path.join(destino, ref))

plugin = os.path.join(RAIZ, "plugins", "founders-os")
with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), encoding="utf-8") as arquivo:
    identidade = json.load(arquivo)
versao = identidade["version"]
manifesto = {
    "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    **identidade,
    "extensions": {"com.openai": {
        "onboardingSkill": "./skills/boas-vindas/SKILL.md",
        "interface": {"displayName": "Founders OS", "shortDescription": identidade["description"]},
    }},
}
with open(os.path.join(plugin, "plugin.json"), "w", encoding="utf-8") as arquivo:
    arquivo.write(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n")
linhas = []
for area in cat["areas"]:
    itens = [s for s in cat["skills"] if s["area"] == area]
    if not itens:
        continue
    linhas.append(f"   **{area}**")
    linhas += [f"   - **{s['nome']}** (`{s['id']}`) — {s['paraQue']}" + (f" {s['onde']}." if s.get("onde") else "") for s in itens]
boas_vindas = f"""---
name: boas-vindas
description: Confirma que o Founders OS está instalado e mostra as skills da Masi Negócios que vêm nele. Use quando o usuário disser "Founders OS", "testar o sistema", "o sistema está funcionando?" ou pedir para ver as skills da Masi Negócios.
---

Responda em português, em tom direto e acolhedor:

1. Diga que a skill de boas-vindas do Founders OS {versao} respondeu. O catálogo completo tem {len(cat['skills'])} skills de negócio. Uma instalação por projeto pode conter apenas uma seleção.
2. No teste de instalação ou quando o usuário pedir a lista, mostre as skills por área. Use o catálogo abaixo para identificar as disponíveis na sessão. Se o ambiente não expuser essa informação, apresente os itens como catálogo.
{chr(10).join(linhas)}
3. Sugira um pedido para uma skill disponível na sessão. Para {cat['skills'][0]['nome']}, por exemplo, use "{cat['skills'][0]['exemplo']}". Se só encontrar boas-vindas, indique o ID de uma skill do catálogo para instalar.
"""
os.makedirs(os.path.join(pasta_skills, "boas-vindas"), exist_ok=True)
open(os.path.join(pasta_skills, "boas-vindas", "SKILL.md"), "w", encoding="utf-8").write(boas_vindas)

campos = ("id", "nome", "area", "icone", "paraQue", "exemplo", "onde")
skills_js = [{k: s[k] for k in campos if k in s} for s in cat["skills"]]
js = ("// Gerado por scripts/gerar.py a partir de catalogo.json. Não edite à mão.\n"
      f"export const AREAS = {json.dumps(cat['areas'], ensure_ascii=False)};\n"
      f"export const SKILLS = {json.dumps(skills_js, ensure_ascii=False, indent=2)};\n")
open(os.path.join(RAIZ, "site", "catalogo.js"), "w", encoding="utf-8").write(js)
print(f"ok: {len(cat['skills'])} skills, versão {versao}")
