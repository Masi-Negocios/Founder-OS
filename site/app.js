// Tela do guia: desenha o estado e repassa cliques para a jornada.
// Nenhuma regra mora aqui; se for preciso perguntar "isso pode?", a resposta está em jornada.js.

import { ICONES } from "./icones.js";
import { TRILHAS, SKILLS, AREAS, MENUS, URL_CLAUDE, MARKETPLACE } from "./conteudo.js";
import {
  estadoInicial,
  concluirPasso,
  desfazerPasso,
  passoLiberado,
  progresso,
  estadoValido,
} from "./jornada.js";
import { carregarProgresso, salvarProgresso, ambienteSalvo, guardarAmbiente } from "./armazenamento.js";

const seletor = document.getElementById("ambiente");
for (const [id, item] of Object.entries(TRILHAS)) seletor.add(new Option(item.nome, id));
const anterior = ambienteSalvo();
let ambiente = Object.hasOwn(TRILHAS, anterior) ? anterior : "codex";
let guia = TRILHAS[ambiente];
function restaurar() {
  const salvo = carregarProgresso(ambiente);
  return estadoValido(salvo, guia.passos) ? salvo : estadoInicial();
}
let estado = restaurar();
seletor.value = ambiente;
seletor.addEventListener("change", () => {
  ambiente = seletor.value;
  guia = TRILHAS[ambiente];
  guardarAmbiente(ambiente);
  estado = restaurar();
  desenhar();
});

const raiz = document.getElementById("passos-area");
const trilha = document.getElementById("indice-passos");
const contador = document.getElementById("contador");
const ajuda = document.getElementById("ajuda-area");

function escapar(texto) {
  return String(texto).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Textos do conteúdo podem ser fixos ou depender dos nomes de menu do idioma escolhido.
function texto(valor, menus) {
  return typeof valor === "function" ? valor(menus) : valor;
}

function situacaoDoPasso(passoId) {
  if (estado.concluidos.includes(passoId)) return "feito";
  return passoLiberado(estado, passoId, guia.passos) ? "atual" : "bloqueado";
}

const visto = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.8"/></svg>';
// Área aberta na vitrine de skills (uma por vez).

function blocoCopiar(conteudo, { endereco = false } = {}) {
  return `
    <div class="copiar${endereco ? " copiar-endereco" : ""}">
      <code>${escapar(conteudo)}</code>
      <button type="button" class="botao botao-copiar" data-copiar="${escapar(conteudo)}">Copiar</button>
    </div>`;
}

// Negrito nos nomes de menu: o conteúdo marca com **assim**, depois de escapado.
function comNegrito(conteudo) {
  return escapar(conteudo).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function figuraDoPrint(imagem) {
  const legenda = "Tela real do Claude";
  return `
    <figure class="print">
      <a href="${imagem.arquivo}" target="_blank" rel="noopener" title="Abrir a imagem em tamanho grande">
        <img src="${imagem.arquivo}" alt="${escapar(imagem.alt)}" loading="lazy">
      </a>
      <figcaption>${legenda}</figcaption>
    </figure>`;
}

function listaDeAcoes(acoes, menus) {
  const itens = acoes.map(
    (a) => `
      <li class="acao">
        <p>${comNegrito(texto(a.texto, menus))}</p>
        ${a.copiar ? blocoCopiar(a.copiar, { endereco: a.copiar === MARKETPLACE }) : ""}
        ${a.imagem ? figuraDoPrint(a.imagem) : ""}
      </li>`
  ).join("");
  return `<ol class="acoes-lista">${itens}</ol>`;
}

function corpoDoPasso(passo, menus) {
  const dica = passo.nota;
  const abreClaude = ["execucao", "catalogo", "testar"].includes(passo.id);
  return `
    ${passo.intro ? `<p class="intro">${escapar(passo.intro)}</p>` : ""}
    ${dica ? `<p class="nota">${escapar(dica)}</p>` : ""}
    ${abreClaude ? `<p><a class="botao botao-claro" href="${URL_CLAUDE}" target="_blank" rel="noopener">Abrir o Claude numa nova aba</a></p>` : ""}
    ${listaDeAcoes(passo.acoes, menus)}
    ${passo.aviso ? `<p class="nota">${escapar(texto(passo.aviso, menus))}</p>` : ""}
    <div class="acoes">
      <button type="button" class="botao botao-escuro" data-concluir="${passo.id}">Feito, próximo passo</button>
    </div>`;
}

function cartaoDoPasso(passo, numero, menus) {
  const situacao = situacaoDoPasso(passo.id);
  const rotuloDesfazer = "Refazer este passo";
  const corpo = {
    atual: `<div class="passo-corpo">${corpoDoPasso(passo, menus)}</div>`,
    feito: `<button type="button" class="link" data-desfazer="${passo.id}">${rotuloDesfazer}</button>`,
    bloqueado: "",
  }[situacao];
  return `
    <li class="passo passo-${situacao}" id="passo-${passo.id}">
      <div class="passo-cabecalho">
        <span class="passo-numero">${situacao === "feito" ? visto : String(numero).padStart(2, "0")}</span>
        <h3>${escapar(passo.titulo)}</h3>
        <span class="passo-tempo">${escapar(passo.tempo)}</span>
      </div>
      ${corpo}
    </li>`;
}

function telaConcluida() {
  return `
    <section class="pronto" id="pronto">
      <p class="sobretitulo">Instalação concluída</p>
      <h2>O Founders OS está pronto para usar em ${escapar(guia.nome)}.</h2>
      <p>Agora é só conversar normalmente. Escolha uma skill abaixo, copie o exemplo e cole num chat novo.</p>
      <a class="botao botao-lima" href="#skills">Ver as skills</a>
    </section>`;
}

function desenharAjuda(menus) {
  const itens = guia.problemas.map(
    (p) => `<details><summary>${escapar(texto(p.sintoma, menus))}</summary><p>${escapar(texto(p.solucao, menus))}
      ${p.link ? `<a href="${escapar(p.link)}">${escapar(p.rotulo)}</a>` : ""}</p></details>`
  ).join("");
  ajuda.innerHTML = `<h2>Travou em algum passo?</h2><div class="ajuda-lista">${itens}</div>
    <p class="recomecar"><button type="button" class="link" data-recomecar>Recomeçar o guia</button></p>`;
}

// --- progresso ---------------------------------------------------------------
// Uma linha com um ponto por passo: feito (visto), da vez (aceso) ou ainda fechado.
function desenharProgresso() {
  const { feitos, total, completo } = progresso(estado, guia.passos);
  contador.textContent = completo ? "Instalação concluída" : `Passo ${feitos + 1} de ${total}`;
  trilha.innerHTML = guia.passos.map((p, i) => {
    const situacao = situacaoDoPasso(p.id);
    return `
      <li class="marco marco-${situacao}"${situacao === "atual" ? ' aria-current="step"' : ""}>
        <span class="marco-ponto">${situacao === "feito" ? visto : i + 1}</span>
        <span class="marco-nome">${escapar(p.titulo)}<small>${escapar(p.tempo)}</small></span>
      </li>`;
  }).join("");

}

// Vitrine: só depende do catálogo. Uma área aberta por vez, uma linha por skill:
// com dezenas de skills, uma grade única vira parede de cartões.
function icone(nome, classe = "") {
  return `<svg class="${classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONES[nome] || ICONES.box}</svg>`;
}

// Vitrine: abas por área em cima e, embaixo, a lista da área aberta no formato de loja
// (ícone, nome, para que serve e "Ver"). No celular a lista corre para o lado, três por coluna.
const COLUNAS = 3;
let areaAberta = AREAS.find((a) => SKILLS.some((s) => s.area === a));
function desenharVitrine() {
  // O total sai do próprio catálogo: skill nova atualiza o número sozinha.
  document.querySelectorAll("[data-total-skills]").forEach((el) => (el.textContent = SKILLS.length));
  const areas = AREAS.filter((a) => SKILLS.some((s) => s.area === a));
  document.getElementById("areas").innerHTML = areas.map((a) => {
    const quantas = SKILLS.filter((s) => s.area === a).length;
    return `<button type="button" class="aba" role="tab" data-area="${escapar(a)}" aria-selected="${a === areaAberta}" aria-controls="skills-painel">${escapar(a)}<small>${quantas}</small></button>`;
  }).join("");
  const itens = SKILLS.map((s, i) => ({ ...s, i })).filter((s) => s.area === areaAberta);
  // Nenhuma linha órfã: com 2 ou 4 skills a lista fecha em duas colunas.
  const colunas = itens.length % COLUNAS === 1 || itens.length < COLUNAS ? 2 : COLUNAS;
  const ultimaLinha = itens.length - (itens.length % colunas || colunas);
  document.getElementById("skills-painel").innerHTML = `
    <ul class="trilho${itens.length <= 3 ? " trilho-curto" : ""}${colunas === 2 ? " trilho-2" : ""}" aria-label="${escapar(areaAberta)}">${itens.map((s, n) => `
      <li class="${n >= ultimaLinha ? "app-fim" : ""}">
        <button type="button" class="app" data-skill="${s.i}" aria-haspopup="dialog">
          <span class="app-icone">${icone(s.icone)}</span>
          <span class="app-texto">
            <strong>${escapar(s.nome)}</strong>
            <span>${escapar(s.paraQue)}</span>
          </span>
          <span class="app-ver">Ver</span>
        </button>
      </li>`).join("")}
    </ul>`;
}

// Ficha da skill: o que ela faz e a frase para mandar depois de instalada. Só abre se a pessoa pedir.
const ficha = document.getElementById("ficha");
function abrirFicha(s) {
  ficha.innerHTML = `
    <div class="ficha-dentro">
      <button type="button" class="ficha-fechar" data-fechar aria-label="Fechar">${icone("x")}</button>
      <header class="ficha-topo">
        <span class="app-icone">${icone(s.icone)}</span>
        <div>
          <h3 id="ficha-nome">${escapar(s.nome)}</h3>
          <p>${escapar(s.area)}${s.onde ? ` · ${escapar(s.onde)}` : ""}</p>
        </div>
      </header>
      <p class="ficha-para">${escapar(s.paraQue)}</p>
      <small>Depois de instalado, mande isto no chat:</small>
      ${blocoCopiar(ambiente === "codex" ? `Use a skill ${s.id} do Founders OS. ${s.exemplo}` : s.exemplo)}
      <a class="botao botao-lima" href="#jornada" data-fechar>Ver instalação</a>
    </div>`;
  ficha.classList.remove("saindo");
  ficha.showModal();
}
function fecharFicha() {
  if (!ficha.open || ficha.classList.contains("saindo")) return;
  const parado = matchMedia("(prefers-reduced-motion: reduce)").matches;
  ficha.classList.add("saindo");
  setTimeout(() => { ficha.close(); ficha.classList.remove("saindo"); }, parado ? 0 : 240);
}
ficha.addEventListener("click", (e) => { if (e.target === ficha || e.target.closest("[data-fechar]")) fecharFicha(); });
ficha.addEventListener("cancel", (e) => { e.preventDefault(); fecharFicha(); });

function desenhar() {
  const menus = MENUS.pt;
  const { completo } = progresso(estado, guia.passos);
  document.getElementById("requisito").textContent = guia.requisito;
  desenharProgresso();
  raiz.innerHTML = `
    <ol class="passos">${guia.passos.map((p, i) => cartaoDoPasso(p, i + 1, menus)).join("")}</ol>
    ${completo ? telaConcluida() : ""}`;
  desenharAjuda(menus);
}

function atualizar(novoEstado, { rolar = true } = {}) {
  estado = novoEstado;
  salvarProgresso(estado, ambiente);
  desenhar();
  if (rolar) document.querySelector(".pronto, .passo-atual")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function copiar(botao) {
  try {
    await navigator.clipboard.writeText(botao.dataset.copiar);
    botao.textContent = "Copiado";
    botao.dataset.copiado = "";
  } catch (erro) {
    // Sem permissão de área de transferência (ex.: página aberta como arquivo): pede cópia manual.
    console.warn("Founders OS: não foi possível copiar automaticamente.", erro);
    botao.textContent = "Selecione e copie";
  }
  setTimeout(() => {
    botao.textContent = "Copiar";
    delete botao.dataset.copiado;
  }, 2000);
}

document.addEventListener("click", (evento) => {
  const alvo = evento.target.closest("button");
  if (!alvo) return;
  const d = alvo.dataset;
  if (d.copiar !== undefined) return copiar(alvo);
  if (d.skill !== undefined) return abrirFicha(SKILLS[Number(d.skill)]);
  if (d.area) {
    areaAberta = d.area;
    return desenharVitrine();
  }
  if (d.concluir) return atualizar(concluirPasso(estado, d.concluir, guia.passos));
  if (d.desfazer) return atualizar(desfazerPasso(estado, d.desfazer, guia.passos));
  if (d.recomecar !== undefined) {
    return atualizar(estadoInicial());
  }
});

desenharVitrine();
desenhar();
