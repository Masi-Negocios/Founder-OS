// Tudo o que o empresário lê no guia mora aqui. A tela (app.js) só desenha;
// mudar um texto, um passo ou uma skill é mexer só neste arquivo.

export const MARKETPLACE = "Masi-Negocios/Founder-OS";
export const URL_CLAUDE = "https://claude.ai";
export const FRASE_TESTE = "testar o Founders OS";

// Nomes dos menus como aparecem no Claude, por idioma da interface dele.
// Conferidos em print do app em português: personalizacao, adicionarMarketplace,
// sincronizarAuto e sincronizar. Os demais ainda precisam de print para confirmar.
export const MENUS = {
  pt: {
    rotulo: "Português",
    personalizacao: "Personalização",
    plugins: "Plugins",
    adicionar: "Adicionar",
    adicionarMarketplace: "Adicionar marketplace",
    sincronizarAuto: "Sincronizar automaticamente",
    sincronizar: "Sincronizar",
    configuracoes: "Configurações",
    capacidades: "Capacidades",
  },
};


// Cada passo é uma lista de ações, uma por linha, na ordem em que o empresário clica.
// `texto` recebe os nomes dos menus no idioma do Claude dele; `imagem` é um print real
// do Claude marcado em laranja (os números da imagem batem com a ordem das ações).
export const PASSOS = [
  {
    id: "execucao",
    titulo: "Ligue a execução de código",
    tempo: "30 s",
    intro: "Ative esta opção para as skills que geram planilhas, documentos ou outros arquivos.",
    acoes: [
      { texto: (m) => `No Claude, abra **${m.configuracoes}**.` },
      { texto: (m) => `Entre em **${m.capacidades}**.` },
      { texto: () => "Ligue a opção de **execução de código e criação de arquivos**." },
    ],
    nota: "Em conta de empresa (Team ou Enterprise), se a opção estiver desligada, peça para quem administra a conta ligar.",
  },
  {
    id: "catalogo",
    titulo: "Adicione o catálogo",
    tempo: "1 min",
    intro: "É aqui que o seu Claude passa a enxergar as skills da Masi Negócios.",
    acoes: [
      {
        texto: (m) => `No menu da esquerda do Claude, clique em **${m.personalizacao}**.`,
        imagem: { arquivo: "/founders-os/img/menu-personalizacao.png", alt: "Menu lateral do Claude com Personalização marcado em laranja" },
      },
      { texto: (m) => `Abra a aba **${m.plugins}**.` },
      { texto: (m) => `Clique em **${m.adicionar}** e escolha **${m.adicionarMarketplace}**.` },
      { texto: () => "Copie o endereço abaixo e cole no campo **URL** (marcado com 1 na imagem).", copiar: MARKETPLACE },
      {
        texto: (m) => `Confira se **${m.sincronizarAuto}** está ligado, em azul (2), e clique em **${m.sincronizar}** (3).`,
        imagem: { arquivo: "/founders-os/img/janela-marketplace.png", alt: "Janela Adicionar marketplace com o campo URL, o botão Sincronizar automaticamente e o botão Sincronizar marcados" },
      },
    ],
    aviso: (m) => `Com “${m.sincronizarAuto}” ligado, o Claude mantém o Sistema atualizado quando a Masi Negócios publicar novidades.`,
  },
  {
    id: "instalar",
    titulo: "Instale o Founders OS",
    tempo: "15 s",
    acoes: [
      { texto: (m) => `Ainda em **${m.personalizacao} › ${m.plugins}**, procure **Founders OS** na lista.` },
      { texto: (m) => `Clique em **${m.adicionar}** ao lado dele.` },
    ],
  },
  {
    id: "testar",
    titulo: "Teste num chat novo",
    tempo: "20 s",
    acoes: [
      { texto: () => "Abra um **chat novo** no Claude." },
      { texto: () => "Copie a frase abaixo, cole no chat e envie.", copiar: FRASE_TESTE },
      { texto: () => "O Claude deve responder que o **Founders OS está instalado** e listar as skills." },
    ],
  },
];

// As skills vêm do catálogo único do repositório (catalogo.json → scripts/gerar.py).
export { SKILLS, AREAS } from "./catalogo.js";

export const PROBLEMAS = [
  {
    sintoma: "Apareceu “Repositório inacessível”",
    solucao: () =>
      "Confira se colou exatamente Masi-Negocios/Founder-OS, sem espaço no começo ou no fim. Use o botão Copiar deste guia. Não é preciso instalar o Claude GitHub App.",
  },
  {
    sintoma: (m) => `Não aparece a opção ${m.plugins}`,
    solucao: (m) => `${m.plugins} só existem nos planos pagos. Confira o seu plano em ${m.configuracoes}.`,
  },
  {
    sintoma: "Enviei a frase de teste e o Claude não reconheceu",
    solucao: (m) =>
      `Abra um chat novo: um chat que já estava aberto não enxerga o que você acabou de instalar. Depois confira em ${m.personalizacao} › ${m.plugins} se o Founders OS aparece como instalado e ativado, e se a execução de código está ligada em ${m.configuracoes} › ${m.capacidades}.`,
  },
  {
    sintoma: "Instalei pela aba de código do app desktop",
    solucao: (m) =>
      `A aba de código (onde aparece “Este computador”) é outro lugar e não atualiza sozinha. Para o dia a dia, instale pelo ${m.personalizacao} › ${m.plugins} do chat.`,
  },
];

const pluginCodex = "founders-os@founders-os";
const exemploCodex = "$founders-os:boas-vindas";
const docDeepSeek = "https://api-docs.deepseek.com/quick_start/agent_integrations/opencode/";
const guiaProjeto = `https://github.com/${MARKETPLACE}#instalar-skills-e-agentes-em-um-projeto`;

export const TRILHAS = {
  codex: {
    nome: "Codex",
    requisito: "Abra o terminal com o Codex CLI instalado. O marketplace disponibiliza o catálogo completo.",
    passos: [
      { id: "codex-catalogo", titulo: "Adicione o marketplace", tempo: "Terminal",
        acoes: [{ texto: "Execute o comando para registrar o repositório da Masi.",
          copiar: `codex plugin marketplace add ${MARKETPLACE}` }] },
      { id: "codex-instalar", titulo: "Instale o plugin", tempo: "Terminal",
        acoes: [{ texto: "Instale o Founders OS pelo nome do catálogo.", copiar: `codex plugin add ${pluginCodex}` }] },
      { id: "codex-testar", titulo: "Teste no Codex", tempo: "No chat",
        acoes: [{ texto: "Abra uma conversa no Codex e peça o catálogo.", copiar: exemploCodex },
          { texto: "Escolha uma skill da sua área e experimente com uma pergunta do negócio." }] },
    ],
    problemas: [
      { sintoma: "Quero instalar uma única skill ou usar um subagente",
        solucao: "A opção --skill aceita o ID da skill e instala o perfil de agente correspondente, quando disponível.",
        link: guiaProjeto, rotulo: "Instalar por projeto" },
      { sintoma: "O comando plugin não aparece no meu Codex",
        solucao: "A instalação por projeto copia as skills para a pasta .agents/skills. Abra o projeto no Codex e peça uma skill pelo nome.",
        link: guiaProjeto, rotulo: "Ver comandos" },
    ],
  },
  opencode: {
    nome: "DeepSeek com OpenCode",
    requisito: "Use um projeto local com Git, Python 3.8 ou superior e OpenCode conectado ao DeepSeek.",
    passos: [
      { id: "opencode-baixar", titulo: "Baixe o Founders OS", tempo: "Terminal",
        acoes: [{ texto: "No terminal, entre na pasta do seu projeto e baixe o repositório.",
          copiar: `git clone https://github.com/${MARKETPLACE}.git` }] },
      { id: "opencode-instalar", titulo: "Instale no projeto", tempo: "Terminal",
        acoes: [{ texto: "Na mesma pasta, instale as skills e os perfis de agente.",
          copiar: "python3 Founder-OS/scripts/instalar.py --ambiente opencode" }] },
      { id: "opencode-testar", titulo: "Chame o primeiro especialista", tempo: "No chat",
        acoes: [{ texto: "Abra o OpenCode nessa pasta, selecione seu modelo DeepSeek e peça o diagnóstico.",
          copiar: "Use o subagente masi-financeiro para me ajudar a montar a DRE do meu negócio." }] },
    ],
    problemas: [
      { sintoma: "Como conecto o DeepSeek ao OpenCode?", solucao: "Siga a configuração de provedor no guia do DeepSeek.",
        link: docDeepSeek, rotulo: "Configurar o provedor DeepSeek" },
      { sintoma: "Estou usando o chat do DeepSeek sem OpenCode",
        solucao: "Cole o conteúdo de SKILL.md como instrução e forneça as referências necessárias à tarefa. Nesse modo a leitura de arquivos é manual." },
    ],
  },
  claude: { nome: "Claude", requisito: "No app do Claude, use uma conta com acesso a plugins.",
    passos: PASSOS, problemas: PROBLEMAS },
};
