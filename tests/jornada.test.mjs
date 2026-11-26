import assert from "node:assert/strict";
import test from "node:test";
import { TRILHAS } from "../site/conteudo.js";
import { concluirPasso, desfazerPasso, estadoInicial, estadoValido, progresso } from "../site/jornada.js";
import { ambienteSalvo, carregarProgresso, guardarAmbiente, salvarProgresso } from "../site/armazenamento.js";

test("cada ambiente exige seus próprios passos em ordem", () => {
  for (const { passos } of Object.values(TRILHAS)) {
    let estado = estadoInicial();
    assert.equal(concluirPasso(estado, passos[1].id, passos), estado);
    for (const passo of passos) estado = concluirPasso(estado, passo.id, passos);
    assert.equal(progresso(estado, passos).completo, true);
    assert.equal(estadoValido(estado, passos), true);
    const reaberto = desfazerPasso(estado, passos[1].id, passos);
    assert.deepEqual(reaberto.concluidos, [passos[0].id]);
  }
});

test("retoma a instalação antiga do Claude e guarda cada ambiente separadamente", () => {
  const dados = new Map();
  globalThis.localStorage = {
    getItem: (chave) => dados.get(chave) ?? null,
    setItem: (chave, valor) => dados.set(chave, valor),
    removeItem: (chave) => dados.delete(chave),
  };
  try {
    assert.equal(ambienteSalvo(), "codex");
    dados.set("founders-os:jornada:v2", JSON.stringify({ concluidos: ["execucao"] }));
    assert.equal(ambienteSalvo(), "claude");
    const antigo = carregarProgresso("claude");
    assert.equal(estadoValido(antigo, TRILHAS.claude.passos), true);
    assert.equal(estadoValido(antigo, TRILHAS.codex.passos), false);
    guardarAmbiente("codex");
    salvarProgresso({ concluidos: ["codex-catalogo"] }, "codex");
    assert.equal(ambienteSalvo(), "codex");
    assert.deepEqual(carregarProgresso("codex").concluidos, ["codex-catalogo"]);
    salvarProgresso(estadoInicial(), "codex");
    assert.equal(carregarProgresso("codex"), null);
    assert.deepEqual(carregarProgresso("claude"), antigo);
  } finally {
    delete globalThis.localStorage;
  }
});
