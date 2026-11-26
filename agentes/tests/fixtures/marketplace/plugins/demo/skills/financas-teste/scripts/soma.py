"""Soma os números de um JSON {"valores": [...]} e grava resultado.txt."""
import json, sys
dados = json.load(open(sys.argv[1], encoding="utf-8"))
total = sum(dados["valores"])
open("resultado.txt", "w", encoding="utf-8").write(str(total))
print("total", total)
