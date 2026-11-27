"""Gera, a partir de catalogo.json, a skill boas-vindas e o site/catalogo.js.
Uso: python3 scripts/gerar.py   (na raiz do repositório)"""
import json, os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat = json.load(open(os.path.join(RAIZ, "catalogo.json"), encoding="utf-8"))
pasta_skills = os.path.join(RAIZ, "plugins", "founders-os", "skills")

# Toda skill do catálogo tem que existir no plugin, e vice-versa: o catálogo não pode mentir.
no_plugin = {d for d in os.listdir(pasta_skills) if os.path.isfile(os.path.join(pasta_skills, d, "SKILL.md"))} - {"boas-vindas"}
no_catalogo = {s["id"] for s in cat["skills"]}
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

versao = json.load(open(os.path.join(RAIZ, "plugins", "founders-os", ".claude-plugin", "plugin.json")))["version"]
linhas = []
for area in cat["areas"]:
    itens = [s for s in cat["skills"] if s["area"] == area]
    if not itens:
        continue
    linhas.append(f"   **{area}**")
    linhas += [f"   - **{s['nome']}**: {s['paraQue']}" + (f" (só no {s['onde']} no computador)" if s.get("onde") else "") for s in itens]
boas_vindas = f"""---
name: boas-vindas
description: Confirma que o Founders OS está instalado e mostra as skills da Masi Negócios que vêm nele. Use quando o usuário disser "Founders OS", "testar o sistema", "o sistema está funcionando?" ou pedir para ver as skills da Masi Negócios.
---

Responda em português, em tom direto e acolhedor:

1. Confirme: "O Founders OS está instalado e funcionando (versão {versao}), com {len(cat['skills'])} skills da Masi Negócios." Esse número já desconta esta skill de boas-vindas: não reconte as pastas nem corrija o total.
2. Liste as skills por área, uma linha cada:
{chr(10).join(linhas)}
3. Termine com um exemplo de pedido que ele pode fazer agora: "{cat['skills'][0]['exemplo']}"
"""
os.makedirs(os.path.join(pasta_skills, "boas-vindas"), exist_ok=True)
open(os.path.join(pasta_skills, "boas-vindas", "SKILL.md"), "w", encoding="utf-8").write(boas_vindas)

campos = ("nome", "area", "icone", "paraQue", "exemplo", "onde")
skills_js = [{k: s[k] for k in campos if k in s} for s in cat["skills"]]

# Pacotes vizinhos: skills da Masi Negócios que moram em outro repositório (ex.: Design Skills). Aparecem na página
# numa aba própria, com o caminho de instalação delas; não entram no plugin nem na boas-vindas.
vizinhos = cat.get("vizinhos", [])
if "--vizinhos" in sys.argv:  # traz de novo a lista publicada de cada vizinho
    import urllib.request
    for v in vizinhos:
        fora = json.load(urllib.request.urlopen(v["catalogo"], timeout=20))
        v["skills"] = [{k: s[k] for k in ("id",) + campos if k in s and k != "area"} for s in fora["skills"]]
    open(os.path.join(RAIZ, "catalogo.json"), "w", encoding="utf-8").write(json.dumps(cat, ensure_ascii=False, indent=2) + "\n")
areas_js = list(cat["areas"])
for v in vizinhos:
    if v["area"] in areas_js:
        sys.exit(f"Área de pacote vizinho repetida: {v['area']}")
    repetidas = no_catalogo & {s["id"] for s in v["skills"]}
    if repetidas:
        sys.exit(f"Skill do vizinho {v['pacote']} com o mesmo id de uma do Founders OS: {sorted(repetidas)}")
    areas_js.append(v["area"])
    pacote = {k: v[k] for k in ("repositorio", "url", "nota") if k in v}
    pacote = {"nome": v["pacote"], **pacote}
    for s in v["skills"]:
        item = {"nome": s["nome"], "area": v["area"]}
        item.update({k: s[k] for k in campos if k in s and k not in item})
        skills_js.append({**item, "pacote": pacote})

js = ("// Gerado por scripts/gerar.py a partir de catalogo.json. Não edite à mão.\n"
      f"export const AREAS = {json.dumps(areas_js, ensure_ascii=False)};\n"
      f"export const SKILLS = {json.dumps(skills_js, ensure_ascii=False, indent=2)};\n")
open(os.path.join(RAIZ, "site", "catalogo.js"), "w", encoding="utf-8").write(js)
print(f"ok: {len(cat['skills'])} skills, versão {versao}" + "".join(f"; vizinho {v['pacote']}: {len(v['skills'])} skills" for v in vizinhos))
