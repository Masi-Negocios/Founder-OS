// Efeitos: só aparência. Não conhece a jornada nem o progresso; se este arquivo falhar,
// o guia continua funcionando inteiro (o CSS só esconde algo quando a classe .movimento existe).

const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Entrada das seções: cada bloco aparece uma vez, quando chega na tela.
function revelar() {
  document.querySelectorAll(".logos li").forEach((el) => el.style.setProperty("--n", [...el.parentElement.children].indexOf(el)));
  const olho = new IntersectionObserver(
    (entradas) => entradas.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("visto");
      olho.unobserve(e.target);
    }),
    { rootMargin: "0px 0px -12% 0px" }
  );
  document.querySelectorAll("[data-revela], .logos").forEach((el) => olho.observe(el));
}

// O chip inclina de leve na direção do ponteiro, como uma peça física sobre a mesa. O transform só
// existe enquanto o ponteiro está na abertura: ao sair, volta a zero e a classe é retirada.
function inclinarChip() {
  const palco = document.querySelector(".chip-palco");
  const hero = document.querySelector(".hero");
  if (!palco || !hero || !window.matchMedia("(pointer: fine)").matches) return;
  let quadro = 0;
  let soltar = 0;
  hero.addEventListener("pointermove", (e) => {
    const caixa = hero.getBoundingClientRect();
    const x = (e.clientX - caixa.left) / caixa.width - 0.5;
    const y = (e.clientY - caixa.top) / caixa.height - 0.5;
    clearTimeout(soltar);
    cancelAnimationFrame(quadro);
    quadro = requestAnimationFrame(() => {
      palco.classList.add("inclina");
      palco.style.setProperty("--ry", `${(x * 14).toFixed(2)}deg`);
      palco.style.setProperty("--rx", `${(-y * 10).toFixed(2)}deg`);
    });
  });
  hero.addEventListener("pointerleave", () => {
    cancelAnimationFrame(quadro);
    palco.style.setProperty("--ry", "0deg");
    palco.style.setProperty("--rx", "0deg");
    soltar = setTimeout(() => palco.classList.remove("inclina"), 460);
  });
}

// O chip acende conforme a página rola e ele entra inteiro na tela.
function ligarChip() {
  const chip = document.querySelector(".chip");
  if (!chip) return;
  let pendente = false;
  const medir = () => {
    pendente = false;
    const caixa = chip.getBoundingClientRect();
    const meio = caixa.top + caixa.height / 2;
    // 0 com o meio do chip no pé da tela, 1 com o meio do chip no meio da tela.
    const aceso = Math.min(1, Math.max(0, (window.innerHeight - meio) / (window.innerHeight / 2)));
    chip.style.setProperty("--aceso", aceso.toFixed(3));
  };
  const pedir = () => {
    if (pendente) return;
    pendente = true;
    requestAnimationFrame(medir);
  };
  window.addEventListener("scroll", pedir, { passive: true });
  window.addEventListener("resize", pedir);
  medir();

}

if (!semMovimento) {
  document.documentElement.classList.add("movimento");
  revelar();
  ligarChip();
  inclinarChip();
}
