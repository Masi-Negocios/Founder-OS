---
name: configurar-maquina
description: "Configura a Máquina de Carrosséis do usuário uma única vez: entrevista curta (nome que aparece nos slides, @ do Instagram, foto de perfil, selo de verificado, negócio, público e tom), publica a página pessoal \"Máquina de Carrosséis\" (prévia dos slides, edição de texto, imagens e download em ZIP) e grava o perfil nela. Use SEMPRE que o usuário disser \"configurar a máquina\", \"instalar a máquina de carrosséis\", \"criar minha máquina\", \"quero começar a fazer carrosséis\", \"trocar minha foto / meu @ / meu nome nos slides\", ou quando qualquer skill da máquina rodar sem encontrar a máquina do usuário. Também para editar um perfil existente.\n"
metadata:
  version: "1.0.0"
---

# /configurar-maquina — o setup de uma vez só

A Máquina é plug and play: o usuário responde poucas perguntas UMA vez, a página dele é publicada com foto, nome e @, e a partir daí todo post sai pronto nela. Fale como alguém montando a mesa de trabalho do usuário: curto, claro, sem jargão técnico (nunca diga "capability", "db", "asset", "JSON"; diga "sua página", "sua máquina", "sua foto").

Com `Artifact` e `ArtifactData` disponíveis, leia `../maquina-de-carrosseis/references/artefato.md` para publicar a página e gravar o perfil. Nos demais ambientes, use o perfil já salvo ou pergunte por negócio, público, tom e nome. Entregue o bloco de perfil da etapa 5 com os dados informados, omitindo o campo Página. Se puder gravar arquivos, salve-o em `carrosseis/perfil.md` no projeto e atualize esse arquivo nas próximas revisões. Retome o pedido original com esse perfil.

## 1. Antes de perguntar, cheque o que já existe

- Se já houver uma máquina deste usuário (ver "Achar a máquina" na referência) e ele veio só trocar foto, @ ou nome: pule para o passo 4 e altere só o que foi pedido.
- Extraia da conversa e do Projeto o que já estiver dito (nome, @, negócio). Só pergunte o que falta.

## 2. Entrevista em uma rodada, no máximo duas

Reúna em uma mensagem as perguntas sobre os campos que faltarem:

1. **Nome nos slides** — como aparece no cabeçalho do slide (ex.: "Breno Masi"). Nome de pessoa ou da marca.
2. **@ do Instagram** — a conta onde os posts saem.
3. **Selo de verificado** — só se a conta do Instagram já tem o selo azul. Opções: não tenho (padrão) / tenho o selo.
4. **Negócio** — o que vende, pra quem e onde, em uma frase (ex.: "fisioterapia para corredores, em Curitiba"). É daqui que saem os temas; quanto mais específico, melhor.
5. **Público** — quem segue o perfil e as 2–3 dores dele, na língua dele ("não consigo cliente", "trabalho demais e não sobra").
6. **Tom** — como o usuário fala: direto e informal (recomendado) / técnico e sóbrio / inspirador.

Depois da entrevista, peça a **foto de perfil** em uma frase: "Agora me manda aqui a foto que vai no círculo do slide (de preferência quadrada, rosto centralizado)." Se o usuário não tiver a foto à mão, siga sem ela e diga que ele pode subir depois clicando no nome dele no topo da página.

Regras: nunca invente resposta pelo usuário; se ele disser "tanto faz" no tom, use direto e informal; o @ começa com "@".

## 3. Publique a máquina

Siga "Publicar a máquina pela primeira vez" na referência: copie o template `assets/maquina-de-carrosseis.html`, publique com `Artifact` e as capabilities indicadas, e guarde a URL.

Se a publicação falhar, entregue o perfil no projeto ou na conversa e informe onde ele pode ser reutilizado.

## 4. Grave o perfil na página

Crie (ou altere, com `if_version`) o documento `settings/profile` com `name`, `handle`, `verified`, `negocio`, `publico`, `tom`, `updatedAt`. Se a foto veio, suba como asset e grave `avatar` e `avatarAsset` (passos na referência).

## 5. Guarde onde achar a máquina depois

- Com Projeto conectado: `project_write` em `maquina-de-carrosseis/maquina.md` com a URL e o bloco de perfil abaixo.
- Com memória disponível: registre "Máquina de Carrosséis do usuário: <URL>".
- Sem nenhum dos dois: diga ao usuário para salvar o link da página (ele também acha pela galeria de artefatos, pelo nome "Máquina de Carrosséis").

Bloco de perfil (formato fixo):
```markdown
# Máquina de Carrosséis
- **Página**: <URL>
- **Nome nos slides**: …
- **Instagram**: @…
- **Selo**: sim | não
- **Negócio**: …
- **Público e dores**: …
- **Tom**: …
```

## 6. Fechamento

Abra a página para o usuário (ela já abre ao publicar) e termine com três linhas, nesta ordem:
1. O que ele está vendo: "Essa é a sua Máquina. Seu perfil já está no topo de cada slide." (Se a foto não veio: "Clique no seu nome no canto para colocar a foto.")
2. O que acontece a partir de agora: "Cada post que você me pedir aparece aí, slide a slide, para você revisar, colocar a imagem e baixar tudo em um clique."
3. O primeiro empurrão: "Quer começar? Me diz um tema, ou fala 'me sugere temas' que eu trago três ideias para o seu público."
