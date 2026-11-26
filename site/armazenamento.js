// Guarda o progresso no próprio navegador do empresário, para ele poder fechar a aba
// e voltar de onde parou. Nada sai da máquina dele: não há servidor nem rastreio.

const CHAVE = "founders-os:jornada:v2";

function chave(ambiente) {
  return ambiente === "claude" ? CHAVE : CHAVE + ":" + ambiente;
}

export function ambienteSalvo() {
  try {
    return localStorage.getItem("founders-os:ambiente") || (localStorage.getItem(CHAVE) ? "claude" : "codex");
  } catch {
    return "codex";
  }
}

export function guardarAmbiente(ambiente) {
  try {
    localStorage.setItem("founders-os:ambiente", ambiente);
  } catch { /* A seleção continua válida nesta aba. */ }
}

export function carregarProgresso(ambiente = "claude") {
  try {
    const bruto = localStorage.getItem(chave(ambiente));
    return bruto ? JSON.parse(bruto) : null;
  } catch (erro) {
    // Navegação privada ou armazenamento bloqueado: o guia funciona, só não lembra.
    console.warn("Founders OS: não foi possível ler o progresso salvo.", erro);
    return null;
  }
}

export function salvarProgresso(estado, ambiente = "claude") {
  if (!estado.concluidos.length) return apagarProgresso(ambiente);
  try {
    localStorage.setItem(chave(ambiente), JSON.stringify(estado));
  } catch (erro) {
    console.warn("Founders OS: não foi possível salvar o progresso.", erro);
  }
}

export function apagarProgresso(ambiente = "claude") {
  try {
    localStorage.removeItem(chave(ambiente));
  } catch (erro) {
    console.warn("Founders OS: não foi possível apagar o progresso.", erro);
  }
}
