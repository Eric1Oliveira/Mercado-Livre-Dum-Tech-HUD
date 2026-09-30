/* O tema do celular: Automático, Claro ou Escuro.
 *
 * Roda ANTES da tela aparecer (script comum no <head>, não module) para que o
 * aparelho no escuro nunca pisque branco. Como a página proíbe script escrito
 * dentro do HTML (Content-Security-Policy), isto tem de morar num arquivo.
 *
 * A escolha fica só neste aparelho. Sem escolha, vale o tema do celular.
 */
(function () {
  "use strict";

  var CHAVE = "dumtech.tema";
  var TEMAS = ["auto", "claro", "escuro"];
  var BARRA = { claro: "#f4f4f8", escuro: "#0e0e14" };
  var raiz = document.documentElement;
  var ouvintes = [];

  function guardado() {
    try {
      var valor = localStorage.getItem(CHAVE);
      return TEMAS.indexOf(valor) > -1 ? valor : "auto";
    } catch (erro) {
      return "auto"; // aba anônima: vale o tema do aparelho
    }
  }

  var atual = guardado();

  function doAparelho() {
    return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
  }

  /** O tema que está de fato na tela agora: "claro" ou "escuro". */
  function efetivo() {
    if (atual === "claro" || atual === "escuro") return atual;
    return doAparelho() ? "escuro" : "claro";
  }

  function pintar() {
    var agora = efetivo();
    raiz.dataset.tema = atual;
    // o CSS so entende "light"/"dark" - escrever "claro" aqui nao faz nada, e
    // o teclado, a barra de rolagem e os controles do sistema saem errados
    raiz.style.colorScheme = agora === "escuro" ? "dark" : "light";
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", BARRA[agora]);
    for (var i = 0; i < ouvintes.length; i++) ouvintes[i](atual, agora);
  }

  function calmo() {
    return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* A troca de tema como uma onda que nasce no próprio botão.
   *
   * O navegador tira uma foto da tela antiga, pinta a nova por baixo e nós só
   * abrimos um círculo por cima: a animação inteira é clip-path na GPU, sem
   * recalcular nada. Onde não existe View Transition (Safari antigo), a cor
   * troca com o fade do CSS - nunca fica seco. */
  function revelar(origem) {
    if (!document.startViewTransition || calmo()) return pintar();

    const area = origem && origem.getBoundingClientRect
      ? origem.getBoundingClientRect()
      : null;
    const x = area ? area.left + area.width / 2 : innerWidth / 2;
    const y = area ? area.top + area.height / 2 : 0;
    // o raio tem de alcançar o canto mais longe da tela
    const raio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));

    let troca;
    try {
      troca = document.startViewTransition(pintar);
    } catch (erro) {
      return pintar();
    }

    /* Rede de seguranca. Quem pinta e a funcao que o navegador chama dentro da
     * transicao - e ele pode demorar, ou descartar a transicao inteira (aba no
     * fundo, outro toque por cima). Se em 300 ms a tela ainda nao for a que o
     * dono escolheu, pinta na marra: a escolha nunca se perde por causa de
     * uma animacao. */
    setTimeout(function () {
      if (raiz.dataset.tema !== atual) pintar();
    }, 300);

    troca.ready.then(function () {
      raiz.animate(
        { clipPath: ["circle(0px at " + x + "px " + y + "px)",
                     "circle(" + raio + "px at " + x + "px " + y + "px)"] },
        { duration: 480, easing: "cubic-bezier(.32, .72, 0, 1)",
          pseudoElement: "::view-transition-new(root)" },
      );
    }).catch(function () { /* transição cancelada: a cor já está certa */ });
    return undefined;
  }

  function definir(tema, origem) {
    atual = TEMAS.indexOf(tema) > -1 ? tema : "auto";
    try {
      if (atual === "auto") localStorage.removeItem(CHAVE);
      else localStorage.setItem(CHAVE, atual);
    } catch (erro) { /* aba anônima: vale até fechar */ }
    revelar(origem);
    return atual;
  }

  /** Automático → Claro → Escuro → Automático. `origem`: de onde a onda nasce. */
  function proximo(origem) {
    return definir(TEMAS[(TEMAS.indexOf(atual) + 1) % TEMAS.length], origem);
  }

  if (typeof matchMedia === "function") {
    var consulta = matchMedia("(prefers-color-scheme: dark)");
    var mudou = function () { if (atual === "auto") pintar(); };
    if (consulta.addEventListener) consulta.addEventListener("change", mudou);
    else if (consulta.addListener) consulta.addListener(mudou);
  }

  window.DumTema = {
    TEMAS: TEMAS,
    atual: function () { return atual; },
    efetivo: efetivo,
    definir: definir,
    proximo: proximo,
    aoMudar: function (funcao) { ouvintes.push(funcao); funcao(atual, efetivo()); },
  };

  pintar();
})();
