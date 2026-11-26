// Regra da jornada: o que está liberado, o que está feito, quanto falta.
// Não toca em DOM nem em armazenamento; recebe e devolve estado puro.

import { PASSOS } from "./conteudo.js";

export function estadoInicial() {
  return { concluidos: [] };
}

export function concluirPasso(estado, passoId, passos = PASSOS) {
  if (!passoLiberado(estado, passoId, passos) || estado.concluidos.includes(passoId)) {
    return estado;
  }
  return { ...estado, concluidos: [...estado.concluidos, passoId] };
}

export function desfazerPasso(estado, passoId, passos = PASSOS) {
  // Desfazer um passo desfaz também os seguintes, que dependiam dele.
  const indice = passos.findIndex((p) => p.id === passoId);
  if (indice < 0) return estado;
  const mantidos = passos.slice(0, indice).map((p) => p.id);
  return { ...estado, concluidos: estado.concluidos.filter((id) => mantidos.includes(id)) };
}

export function passoLiberado(estado, passoId, passos = PASSOS) {
  const indice = passos.findIndex((p) => p.id === passoId);
  if (indice <= 0) return indice === 0;
  return passos.slice(0, indice).every((p) => estado.concluidos.includes(p.id));
}

export function progresso(estado, passos = PASSOS) {
  const feitos = passos.filter((p) => estado.concluidos.includes(p.id)).length;
  return { feitos, total: passos.length, completo: feitos === passos.length };
}

export function estadoValido(estado, passos = PASSOS) {
  return (
    estado !== null &&
    typeof estado === "object" &&
    Array.isArray(estado.concluidos) &&
    estado.concluidos.every((id, i) => passos[i]?.id === id)
  );
}
