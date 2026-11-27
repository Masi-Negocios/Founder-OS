// Interface de conversa com os agentes do Founders OS. Sem build: módulo ES puro.
import { ICONES } from "/site/icones.js";

const CHAVE_LOCAL = "founders-agentes:chave";
const RECEPCAO = "recepcao";
const $ = (id) => document.getElementById(id);

const estado = {
  agentes: [],
  areas: [],
  times: [],
  agente: RECEPCAO,
  sessao: null,
  modo: "conversa",
  selecionados: new Set(),
  modelo: "",
  ocupado: false,
  chave: lerLocal(CHAVE_LOCAL),
};

function lerLocal(chave) {
  try { return localStorage.getItem(chave) || ""; } catch { return ""; }
}
function gravarLocal(chave, valor) {
  try { localStorage.setItem(chave, valor); } catch { /* navegador sem armazenamento: segue sem lembrar */ }
}

// --- API ---------------------------------------------------------------------
class SemChave extends Error {}

async function api(caminho, { metodo = "GET", corpo } = {}) {
  const cabecalhos = {};
  if (estado.chave) cabecalhos.Authorization = `Bearer ${estado.chave}`;
  if (corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
  const resposta = await fetch(caminho, { method: metodo, headers: cabecalhos, body: corpo === undefined ? undefined : JSON.stringify(corpo) });
  if (resposta.status === 401) throw new SemChave();
  if (!resposta.ok) {
    let mensagem = `HTTP ${resposta.status}`;
    try { mensagem = (await resposta.json()).error?.message || mensagem; } catch { /* corpo sem JSON */ }
    throw new Error(mensagem);
  }
  return resposta;
}

async function comChave(acao) {
  try {
    return await acao();
  } catch (erro) {
    if (!(erro instanceof SemChave)) throw erro;
    await pedirChave();
    return acao();
  }
}

function pedirChave() {
  return new Promise((resolver) => {
    const dialogo = $("dialogo-chave");
    $("campo-chave").value = "";
    dialogo.addEventListener("close", () => {
      estado.chave = $("campo-chave").value.trim();
      gravarLocal(CHAVE_LOCAL, estado.chave);
      resolver();
    }, { once: true });
    dialogo.showModal();
  });
}

async function* eventosSSE(resposta) {
  const leitor = resposta.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buffer += decodificador.decode(value, { stream: true });
    let fim;
    while ((fim = buffer.indexOf("\n\n")) >= 0) {
      const bloco = buffer.slice(0, fim);
      buffer = buffer.slice(fim + 2);
      let tipo = "message";
      let dados = "";
      for (const linha of bloco.split("\n")) {
        if (linha.startsWith("event:")) tipo = linha.slice(6).trim();
        else if (linha.startsWith("data:")) dados += linha.slice(5).trimStart();
      }
      if (dados) yield { tipo, dados: JSON.parse(dados) };
    }
  }
}

// --- ícones e markdown --------------------------------------------------------
function icone(nome) {
  const desenho = ICONES[nome] || ICONES["box"] || "";
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${desenho}</svg>`;
}

function escapar(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function inline(texto) {
  return escapar(texto)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/(^|[\s(])_([^_\s][^_]*)_/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/)[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function markdown(texto) {
  const linhas = String(texto || "").replace(/\r/g, "").split("\n");
  const saida = [];
  let i = 0;
  const celulas = (linha) => linha.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  while (i < linhas.length) {
    const linha = linhas[i];
    if (/^```/.test(linha)) {
      const codigo = [];
      i++;
      while (i < linhas.length && !/^```/.test(linhas[i])) codigo.push(linhas[i++]);
      i++;
      saida.push(`<pre><code>${escapar(codigo.join("\n"))}</code></pre>`);
      continue;
    }
    if (/^\s*$/.test(linha)) { i++; continue; }
    const titulo = linha.match(/^(#{1,6})\s+(.*)$/);
    if (titulo) { const n = Math.min(titulo[1].length + 1, 4); saida.push(`<h${n}>${inline(titulo[2])}</h${n}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(linha)) { saida.push("<hr>"); i++; continue; }
    if (/^\s*\|/.test(linha) && i + 1 < linhas.length && /^\s*\|?\s*:?-{2,}/.test(linhas[i + 1])) {
      const cabeca = celulas(linha);
      i += 2;
      const corpo = [];
      while (i < linhas.length && /^\s*\|/.test(linhas[i])) corpo.push(celulas(linhas[i++]));
      saida.push(`<table><thead><tr>${cabeca.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${corpo
        .map((l) => `<tr>${l.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    if (/^\s*>/.test(linha)) {
      const citacao = [];
      while (i < linhas.length && /^\s*>/.test(linhas[i])) citacao.push(linhas[i++].replace(/^\s*>\s?/, ""));
      saida.push(`<blockquote>${markdown(citacao.join("\n"))}</blockquote>`);
      continue;
    }
    const lista = linha.match(/^\s*([-*+]|\d+[.)])\s+/);
    if (lista) {
      const ordenada = /\d/.test(lista[1]);
      const itens = [];
      while (i < linhas.length && /^\s*([-*+]|\d+[.)])\s+/.test(linhas[i])) {
        let item = linhas[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, "");
        while (i < linhas.length && /^\s{2,}\S/.test(linhas[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(linhas[i])) item += " " + linhas[i++].trim();
        itens.push(`<li>${inline(item)}</li>`);
      }
      const inicio = ordenada ? parseInt(lista[1], 10) : 1;
      saida.push(ordenada ? `<ol${inicio > 1 ? ` start="${inicio}"` : ""}>${itens.join("")}</ol>` : `<ul>${itens.join("")}</ul>`);
      continue;
    }
    const paragrafo = [];
    while (i < linhas.length && !/^\s*$/.test(linhas[i]) && !/^(#{1,6}\s|```|\s*>|\s*([-*+]|\d+[.)])\s+|\s*\|)/.test(linhas[i])) paragrafo.push(linhas[i++]);
    if (!paragrafo.length) paragrafo.push(linhas[i++]);
    saida.push(`<p>${paragrafo.map(inline).join("<br>")}</p>`);
  }
  return saida.join("");
}

// --- lista de agentes -----------------------------------------------------------
function agentePorId(id) {
  return estado.agentes.find((a) => a.id === id);
}

function desenharLista() {
  const filtro = $("busca").value.trim().toLocaleLowerCase("pt-BR").normalize("NFD").replace(/\p{M}/gu, "");
  const casa = (a) => !filtro || `${a.nome} ${a.paraQue} ${a.id}`.toLocaleLowerCase("pt-BR").normalize("NFD").replace(/\p{M}/gu, "").includes(filtro);
  const lista = $("lista");
  lista.classList.toggle("conselho", estado.modo === "conselho");
  const grupos = [];
  const recepcao = agentePorId(RECEPCAO);
  if (estado.modo === "conversa" && recepcao && casa(recepcao)) grupos.push(["Entrada", [recepcao]]);
  const areas = [...estado.areas, ...new Set(estado.agentes.map((a) => a.area || "Outros").filter((a) => !estado.areas.includes(a)))];
  for (const area of areas) {
    const itens = estado.agentes.filter((a) => a.tipo !== "interno" && (a.area || "Outros") === area && casa(a));
    if (itens.length) grupos.push([area, itens]);
  }
  lista.innerHTML = grupos.map(([area, itens]) => `
    <section class="area"><h3>${escapar(area)}</h3>
      ${itens.map((a) => `
        <button class="item" type="button" data-id="${escapar(a.id)}" ${a.disponivel ? "" : "disabled"}
          title="${escapar(a.disponivel ? a.paraQue : a.motivoIndisponivel)}"
          ${estado.modo === "conselho" ? `aria-pressed="${estado.selecionados.has(a.id)}"` : `aria-current="${a.id === estado.agente}"`}>
          <span class="item-icone">${icone(a.icone)}</span>
          <span class="item-texto"><span class="item-nome">${escapar(a.nome)}</span><span class="item-sub">${escapar(a.paraQue || "")}</span></span>
          <span class="item-marca" aria-hidden="true"></span>
        </button>`).join("")}
    </section>`).join("") || `<p class="item-sub" style="padding:12px">Nenhum agente encontrado.</p>`;
}

function desenharTimes() {
  const caixa = $("times");
  caixa.hidden = estado.modo !== "conselho" || !estado.times.length;
  caixa.innerHTML = estado.times.map((t) => `<button type="button" data-time="${escapar(t.id)}" title="${escapar(t.descricao)}">${escapar(t.nome)}</button>`).join("");
}

function desenharCabecalho() {
  const alvo = $("agente-atual");
  if (estado.modo === "conselho") {
    const nomes = [...estado.selecionados].map((id) => agentePorId(id)?.nome).filter(Boolean);
    alvo.innerHTML = `<span class="item-icone">${icone("users-round")}</span><div><h1>Conselho</h1>
      <p>${nomes.length ? escapar(nomes.join(" · ")) : "Escolha de 2 a 6 agentes na lista ou um time"}</p></div>`;
    return;
  }
  const a = agentePorId(estado.agente) || agentePorId(RECEPCAO);
  alvo.innerHTML = `<span class="item-icone">${icone(a?.icone)}</span><div><h1>${escapar(a?.nome || "Agente")}</h1>
    <p>${escapar(a?.paraQue || "")}</p></div>`;
}

function escolherAgente(id) {
  if (estado.modo === "conselho") {
    if (estado.selecionados.has(id)) estado.selecionados.delete(id);
    else if (estado.selecionados.size < 6) estado.selecionados.add(id);
  } else {
    if (estado.agente !== id && estado.sessao) novaConversa();
    estado.agente = id;
    if (!$("mensagens").querySelector(".msg")) telaVazia();
  }
  desenharLista();
  desenharCabecalho();
  document.getElementById("app").classList.remove("lateral-aberta");
  $("entrada").focus();
}

function mudarModo(modo) {
  estado.modo = modo;
  $("modo-conversa").setAttribute("aria-selected", String(modo === "conversa"));
  $("modo-conselho").setAttribute("aria-selected", String(modo === "conselho"));
  $("entrada").placeholder = modo === "conselho" ? "Qual decisão você quer levar ao conselho?" : "Conte o que você precisa";
  novaConversa();
  desenharTimes();
  desenharLista();
  desenharCabecalho();
}

// --- mensagens ---------------------------------------------------------------
function rolar() {
  if (estado.rolagemFixa) return;  // um link pediu outra posição; volta ao normal na próxima mensagem
  const caixa = $("mensagens");
  caixa.scrollTop = caixa.scrollHeight;
}

function telaVazia() {
  const a = estado.modo === "conselho" ? null : agentePorId(estado.agente);
  const exemplos = estado.modo === "conselho"
    ? ["Vale a pena abrir uma segunda unidade agora?", "Devo subir o preço em 15% no ano que vem?"]
    : a && a.id !== RECEPCAO && a.exemplo
      ? [a.exemplo]
      : estado.agentes.filter((x) => x.exemplo && x.tipo !== "interno" && x.disponivel).slice(0, 4).map((x) => x.exemplo);
  $("mensagens").innerHTML = `<div class="vazio">
    <h2>${estado.modo === "conselho" ? "Leve uma decisão ao conselho" : escapar(a?.id === RECEPCAO ? "Com o que posso ajudar?" : a?.nome || "")}</h2>
    <p>${estado.modo === "conselho"
      ? "Cada agente responde da sua área e o moderador junta tudo numa recomendação."
      : a?.id === RECEPCAO
        ? "Conte o que você precisa: a Recepção chama o especialista certo do Founders OS."
        : escapar(a?.paraQue || "")}</p>
    <div class="exemplos">${exemplos.map((e) => `<button type="button" data-exemplo="${escapar(e)}">${escapar(e)}</button>`).join("")}</div>
  </div>`;
}

function novaConversa() {
  estado.sessao = null;
  atualizarEndereco(null);
  telaVazia();
  desenharCabecalho();
}

// O endereço guarda a conversa aberta: recarregar a página ou mandar o link reabre a mesma conversa.
function atualizarEndereco(sessao) {
  const endereco = sessao ? `?sessao=${encodeURIComponent(sessao)}` : location.pathname;
  if (location.search !== (sessao ? endereco : "")) history.replaceState(null, "", endereco);
}

function desenharConselho(membros) {
  const grade = document.createElement("div");
  grade.className = "conselho-grade";
  const cartoes = new Map();
  for (const m of membros) {
    const cartao = document.createElement("article");
    cartao.className = "membro md";
    cartao.innerHTML = `<h4>${escapar(m.nome)}</h4><div class="corpo digitando"></div>`;
    grade.append(cartao);
    cartoes.set(m.agente, { cartao, texto: "" });
  }
  $("mensagens").append(grade);
  rolar();
  return cartoes;
}

function adicionarUsuario(texto) {
  $("mensagens").querySelector(".vazio")?.remove();
  const el = document.createElement("div");
  el.className = "msg msg-usuario";
  el.innerHTML = `<div class="bolha"></div>`;
  el.querySelector(".bolha").textContent = texto;
  $("mensagens").append(el);
  rolar();
}

function criarBolhaAgente(agente) {
  const el = document.createElement("div");
  el.className = "msg msg-agente";
  el.innerHTML = `<div class="rotulo"><b>${escapar(agente.nome || "Agente")}</b>${agente.modelo ? `<span class="modelo">${escapar(agente.modelo)}</span>` : ""}</div>
    <div class="eventos"></div><div class="bolha md digitando"></div><div class="arquivos"></div>`;
  $("mensagens").append(el);
  const bolha = { el, texto: "", agendado: false };
  bolha.render = () => {
    if (bolha.agendado) return;
    bolha.agendado = true;
    requestAnimationFrame(() => {
      bolha.agendado = false;
      el.querySelector(".bolha").innerHTML = markdown(bolha.texto);
      rolar();
    });
  };
  return bolha;
}

function adicionarEvento(bolha, texto, classe = "") {
  if (!bolha) return;
  const linha = document.createElement("div");
  linha.className = `evento ${classe}`;
  linha.textContent = texto;
  bolha.el.querySelector(".eventos").append(linha);
  rolar();
}

function adicionarArquivo(bolha, arquivo) {
  if (!bolha) return;
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "arquivo";
  botao.textContent = `⬇ ${arquivo.nome}`;
  botao.addEventListener("click", () => baixar(arquivo).catch((e) => alert(e.message)));
  bolha.el.querySelector(".arquivos").append(botao);
}

async function baixar(arquivo) {
  const resposta = await comChave(() => api(arquivo.url));
  const url = URL.createObjectURL(await resposta.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: arquivo.nome });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

const ROTULOS = {
  ler_arquivo_skill: (a) => `Lendo ${a.caminho || "um arquivo da skill"}`,
  listar_arquivos_skill: () => "Olhando os arquivos da skill",
  carregar_skill: (a) => `Carregando a skill ${nomeDe(a.skill)}`,
  passar_para_agente: (a) => `Chamando ${nomeDe(a.agente)}`,
  consultar_agente: (a) => `Consultando ${nomeDe(a.agente)}`,
  atualizar_perfil: () => "Guardando no perfil do negócio",
  salvar_arquivo: (a) => `Salvando ${a.nome || "arquivo"}`,
  executar_script: (a) => `Rodando ${a.script || "script"}`,
};
function nomeDe(id) {
  return agentePorId(id)?.nome || id || "";
}

// --- envio -------------------------------------------------------------------
async function enviar(texto) {
  texto = texto.trim();
  if (!texto || estado.ocupado) return;
  if (estado.modo === "conselho" && estado.selecionados.size < 2) {
    alert("Escolha de 2 a 6 agentes (ou um time) para o conselho.");
    return;
  }
  estado.ocupado = true;
  estado.rolagemFixa = false;
  $("enviar").disabled = true;
  $("entrada").value = "";
  ajustarAltura();
  $("sugestoes").hidden = true;
  adicionarUsuario(texto);

  const conselho = estado.modo === "conselho";
  const caminho = conselho ? "/v1/conselho" : "/v1/conversa";
  const corpo = conselho
    ? { pergunta: texto, agentes: [...estado.selecionados], sessaoId: estado.sessao || undefined, modelo: estado.modelo || undefined, stream: true }
    : { mensagem: texto, sessaoId: estado.sessao || undefined, agente: estado.sessao ? undefined : estado.agente, modelo: estado.modelo || undefined, stream: true };

  let bolha = null;
  const membros = new Map();
  try {
    const resposta = await comChave(() => api(caminho, { metodo: "POST", corpo }));
    for await (const { tipo, dados } of eventosSSE(resposta)) {
      switch (tipo) {
        case "sessao":
          estado.sessao = dados.sessaoId;
          atualizarEndereco(dados.sessaoId);
          break;
        case "agente":
          bolha?.el.querySelector(".bolha").classList.remove("digitando");
          bolha = criarBolhaAgente(dados);
          if (!conselho) { estado.agente = dados.agente; desenharCabecalho(); desenharLista(); }
          break;
        case "passagem": {
          bolha?.el.querySelector(".bolha").classList.remove("digitando");
          if (bolha && !bolha.texto) bolha.el.querySelector(".bolha").remove();
          const aviso = document.createElement("div");
          aviso.className = "passagem";
          aviso.textContent = `${dados.deNome} passou a conversa para ${dados.nome}`;
          $("mensagens").append(aviso);
          bolha = criarBolhaAgente(dados);
          estado.agente = dados.agente;
          desenharCabecalho();
          desenharLista();
          break;
        }
        case "texto":
          if (!bolha) bolha = criarBolhaAgente({ nome: agentePorId(dados.agente)?.nome });
          bolha.texto += dados.delta;
          bolha.render();
          break;
        case "reinicio":
          if (bolha) { bolha.texto = ""; bolha.render(); }
          break;
        case "ferramenta":
          adicionarEvento(bolha, (ROTULOS[dados.nome] || (() => dados.nome))(dados.argumentos || {}));
          break;
        case "ferramenta_fim":
          if (!dados.ok) adicionarEvento(bolha, `${dados.nome} falhou: ${dados.resumo}`, "alerta");
          break;
        case "consulta":
          break;
        case "arquivo":
          adicionarArquivo(bolha, dados);
          break;
        case "aviso":
          adicionarEvento(bolha, dados.mensagem, "alerta");
          break;
        case "erro":
          if (!bolha) bolha = criarBolhaAgente({ nome: "Founders OS" });
          adicionarEvento(bolha, dados.mensagem, "erro");
          break;
        case "recusa":
          adicionarEvento(bolha, "O modelo recusou este pedido.", "alerta");
          break;
        case "conselho":
          for (const [id, cartao] of desenharConselho(dados.membros)) membros.set(id, cartao);
          break;
        case "membro_texto": {
          const m = membros.get(dados.agente);
          if (m) { m.texto += dados.delta; m.cartao.querySelector(".corpo").innerHTML = markdown(m.texto); }
          break;
        }
        case "membro_fim": {
          const m = membros.get(dados.agente);
          if (m) {
            m.cartao.classList.add("pronto");
            m.cartao.querySelector(".corpo").classList.remove("digitando");
            m.cartao.querySelector(".corpo").innerHTML = markdown(dados.texto);
          }
          break;
        }
        case "fim":
          if (dados.sessaoId) estado.sessao = dados.sessaoId;
          break;
        default:
          break;
      }
    }
  } catch (erro) {
    if (!bolha) bolha = criarBolhaAgente({ nome: "Founders OS" });
    adicionarEvento(bolha, erro.message || String(erro), "erro");
  } finally {
    document.querySelectorAll(".digitando").forEach((el) => el.classList.remove("digitando"));
    estado.ocupado = false;
    $("enviar").disabled = false;
    $("entrada").focus();
  }
}

// --- sugestões de agente enquanto digita ---------------------------------------
let temporizador = null;
function sugerir() {
  clearTimeout(temporizador);
  const texto = $("entrada").value.trim();
  if (estado.modo !== "conversa" || estado.agente !== RECEPCAO || estado.sessao || texto.length < 12) {
    $("sugestoes").hidden = true;
    return;
  }
  temporizador = setTimeout(async () => {
    try {
      const dados = await (await api(`/v1/sugerir?q=${encodeURIComponent(texto)}&limite=3`)).json();
      const caixa = $("sugestoes");
      caixa.hidden = !dados.sugestoes.length;
      caixa.innerHTML = `Ir direto para: ${dados.sugestoes.map((s) => `<button type="button" data-id="${escapar(s.agente)}">${escapar(s.nome)}</button>`).join("")}`;
    } catch { /* sugestão é opcional */ }
  }, 350);
}

function ajustarAltura() {
  const campo = $("entrada");
  campo.style.height = "auto";
  campo.style.height = `${Math.min(campo.scrollHeight, 220)}px`;
}

// --- perfil e histórico ---------------------------------------------------------
async function abrirPerfil() {
  const { perfil } = await (await comChave(() => api("/v1/perfil"))).json();
  const campos = $("campos-perfil");
  campos.innerHTML = "";
  const entradas = Object.entries(perfil);
  (entradas.length ? entradas : [["o_que_vende", ""], ["faturamento_mensal", ""], ["tamanho_do_time", ""]]).forEach(([k, v]) => adicionarCampo(k, v));
  $("dialogo-perfil").showModal();
}

function adicionarCampo(chave = "", valor = "") {
  const linha = document.createElement("div");
  linha.className = "campo";
  linha.innerHTML = `<input class="chave" placeholder="campo" value="${escapar(chave)}"><input class="valor" placeholder="valor" value="${escapar(valor)}">`;
  $("campos-perfil").append(linha);
}

async function salvarPerfil() {
  const perfil = {};
  for (const linha of $("campos-perfil").querySelectorAll(".campo")) {
    const chave = linha.querySelector(".chave").value.trim();
    if (chave) perfil[chave] = linha.querySelector(".valor").value.trim();
  }
  await comChave(() => api("/v1/perfil", { metodo: "PUT", corpo: { perfil, substituir: true } }));
}

async function abrirHistorico() {
  const { sessoes } = await (await comChave(() => api("/v1/sessoes"))).json();
  const lista = $("lista-historico");
  lista.innerHTML = sessoes.length
    ? sessoes.map((s) => `<li><button type="button" data-sessao="${escapar(s.id)}">${escapar(s.titulo || "Sem título")}
        <small>${escapar(nomeDe(s.agenteAtual) || "Recepção")} · ${new Date(s.atualizadaEm).toLocaleString("pt-BR")}</small></button></li>`).join("")
    : "<li><small>Nenhuma conversa ainda.</small></li>";
  $("dialogo-historico").showModal();
}

async function abrirSessao(id) {
  const dados = await (await comChave(() => api(`/v1/sessoes/${encodeURIComponent(id)}`))).json();
  if (estado.modo !== "conversa") mudarModo("conversa");
  estado.sessao = dados.id;
  estado.agente = dados.agenteAtual || RECEPCAO;
  $("mensagens").innerHTML = "";
  // Rodadas seguidas do mesmo agente viram um balão só, como na conversa ao vivo.
  const bolhas = [];
  let anterior = null;
  let membros = null;
  for (const m of dados.mensagens) {
    if (m.papel === "usuario") { adicionarUsuario(m.texto); anterior = null; continue; }
    if (m.conselho) {
      const cartoes = desenharConselho(Object.keys(m.conselho).map((id) => ({ agente: id, nome: nomeDe(id) })));
      for (const [id, { cartao }] of cartoes) {
        cartao.classList.add("pronto");
        const corpo = cartao.querySelector(".corpo");
        corpo.classList.remove("digitando");
        corpo.innerHTML = markdown(m.conselho[id]);
      }
      membros = Object.keys(m.conselho);
      anterior = null;
    }
    if (anterior && anterior.agente !== m.agente) {
      const aviso = document.createElement("div");
      aviso.className = "passagem";
      aviso.textContent = `${nomeDe(anterior.agente)} passou a conversa para ${nomeDe(m.agente)}`;
      $("mensagens").append(aviso);
    }
    let bolha = anterior?.agente === m.agente ? anterior.bolha : null;
    if (!bolha) {
      bolha = criarBolhaAgente({ nome: m.agente === "conselho" ? "Conselho" : nomeDe(m.agente), modelo: m.modelo });
      bolha.el.querySelector(".bolha").classList.remove("digitando");
      bolhas.push(bolha);
    }
    for (const f of m.ferramentas || []) {
      const nome = typeof f === "string" ? f : f.nome;
      adicionarEvento(bolha, (ROTULOS[nome] || (() => nome))(f.argumentos || {}));
    }
    if ((m.texto || "").trim()) {
      bolha.texto += (bolha.texto ? "\n\n" : "") + m.texto;
      bolha.render();
    }
    anterior = { agente: m.agente, bolha };
  }
  for (const bolha of bolhas) if (!bolha.texto) bolha.el.querySelector(".bolha").remove();
  if (membros) {
    // Conversa de Conselho: reabre no modo Conselho, com os mesmos membros, para seguir perguntando ao grupo.
    estado.modo = "conselho";
    estado.selecionados = new Set(membros);
    $("modo-conversa").setAttribute("aria-selected", "false");
    $("modo-conselho").setAttribute("aria-selected", "true");
    $("entrada").placeholder = "Qual decisão você quer levar ao conselho?";
    desenharTimes();
  }
  if (dados.arquivos?.length) {
    const bolha = criarBolhaAgente({ nome: "Arquivos desta conversa" });
    bolha.el.querySelector(".bolha").remove();
    for (const arquivo of dados.arquivos) adicionarArquivo(bolha, arquivo);
  }
  atualizarEndereco(dados.id);
  desenharCabecalho();
  desenharLista();
}

// Links diretos: ?agente=<id>, ?modo=conselho&time=<id>, ?sessao=<id>, ?abrir=perfil|historico, ?tema=claro|escuro
async function abrirPeloEndereco() {
  const params = new URLSearchParams(location.search);
  const tema = { claro: "light", escuro: "dark" }[params.get("tema")];
  if (tema) document.documentElement.dataset.theme = tema;
  if (params.get("modo") === "conselho") {
    mudarModo("conselho");
    const time = estado.times.find((t) => t.id === params.get("time"));
    if (time) {
      estado.selecionados = new Set(time.agentes.slice(0, 6));
      desenharLista();
      desenharCabecalho();
    }
  } else if (agentePorId(params.get("agente"))?.disponivel) {
    escolherAgente(params.get("agente"));
  }
  if (params.get("sessao")) {
    const posicao = params.get("rolar");
    estado.rolagemFixa = posicao === "topo" || posicao === "tabela";
    await abrirSessao(params.get("sessao"));
    if (estado.rolagemFixa) {
      // depois dos renders agendados pelos balões
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const caixa = $("mensagens");
        const tabela = posicao === "tabela" && caixa.querySelector(".md table");
        caixa.scrollTop = tabela ? tabela.getBoundingClientRect().top - caixa.getBoundingClientRect().top + caixa.scrollTop - 120 : 0;
      }));
    }
  }
  if (params.get("abrir") === "perfil") await abrirPerfil();
  if (params.get("abrir") === "historico") await abrirHistorico();
}

// --- modelos ----------------------------------------------------------------------
async function carregarModelos() {
  const dados = await (await api("/v1/provedores")).json();
  const opcoes = [["", `Padrão · ${dados.modeloPadrao}`]];
  for (const [apelido, ref] of Object.entries(dados.apelidos || {})) opcoes.push([apelido, `${apelido} · ${ref}`]);
  const select = $("modelo");
  select.innerHTML = opcoes.map(([v, t]) => `<option value="${escapar(v)}">${escapar(t)}</option>`).join("");
  select.value = estado.modelo;
}

// --- início ----------------------------------------------------------------------
async function iniciar() {
  try {
    const dados = await (await comChave(() => api("/v1/agentes"))).json();
    estado.agentes = dados.agentes;
    estado.areas = dados.areas;
    estado.times = (await (await api("/v1/times")).json()).times;
    await carregarModelos();
  } catch (erro) {
    $("mensagens").innerHTML = `<div class="vazio"><h2>Não consegui falar com o servidor</h2><p>${escapar(erro.message)}</p></div>`;
    return;
  }
  desenharLista();
  desenharCabecalho();
  telaVazia();

  $("lista").addEventListener("click", (e) => {
    const item = e.target.closest(".item");
    if (item && !item.disabled) escolherAgente(item.dataset.id);
  });
  $("times").addEventListener("click", (e) => {
    const botao = e.target.closest("[data-time]");
    if (!botao) return;
    const time = estado.times.find((t) => t.id === botao.dataset.time);
    estado.selecionados = new Set(time.agentes.slice(0, 6));
    desenharLista();
    desenharCabecalho();
  });
  $("busca").addEventListener("input", desenharLista);
  $("modo-conversa").addEventListener("click", () => mudarModo("conversa"));
  $("modo-conselho").addEventListener("click", () => mudarModo("conselho"));
  $("nova").addEventListener("click", () => { estado.agente = estado.modo === "conversa" ? RECEPCAO : estado.agente; novaConversa(); desenharLista(); });
  $("modelo").addEventListener("change", (e) => { estado.modelo = e.target.value; });
  $("compositor").addEventListener("submit", (e) => { e.preventDefault(); enviar($("entrada").value); });
  $("entrada").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar($("entrada").value); }
  });
  $("entrada").addEventListener("input", () => { ajustarAltura(); sugerir(); });
  $("sugestoes").addEventListener("click", (e) => {
    const botao = e.target.closest("[data-id]");
    if (botao) { escolherAgente(botao.dataset.id); $("sugestoes").hidden = true; }
  });
  $("mensagens").addEventListener("click", (e) => {
    const exemplo = e.target.closest("[data-exemplo]");
    if (exemplo) enviar(exemplo.dataset.exemplo);
  });
  $("abrir-perfil").addEventListener("click", () => abrirPerfil().catch((e) => alert(e.message)));
  $("novo-campo").addEventListener("click", () => adicionarCampo());
  $("dialogo-perfil").addEventListener("close", () => {
    if ($("dialogo-perfil").returnValue === "salvar") salvarPerfil().catch((e) => alert(e.message));
  });
  $("abrir-historico").addEventListener("click", () => abrirHistorico().catch((e) => alert(e.message)));
  $("lista-historico").addEventListener("click", (e) => {
    const botao = e.target.closest("[data-sessao]");
    if (botao) { $("dialogo-historico").close(); abrirSessao(botao.dataset.sessao).catch((err) => alert(err.message)); }
  });
  $("abrir-lateral").addEventListener("click", () => $("app").classList.add("lateral-aberta"));
  $("fechar-lateral").addEventListener("click", () => $("app").classList.remove("lateral-aberta"));
  $("entrada").focus();
  abrirPeloEndereco().catch(() => atualizarEndereco(null));
}

iniciar();
