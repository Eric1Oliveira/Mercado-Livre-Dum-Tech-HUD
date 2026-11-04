// A pagina inicial do plano mensal: liga os motores (plano.js e conteudo.js)
// na tela. Regra de negocio nenhuma mora aqui.
//
// O que vem do painel: precos, planos prontos, adicionais a venda, quais
// combinacoes tem link, os textos publicados e a faixa de aviso - tudo por
// dumtech_mensalidade_publica. Enquanto ela nao responde, a pagina pinta com o
// padrao (plano.js e conteudo.js).
//
// Quem e VITALICIO nunca e empurrado para a mensalidade: a pagina esconde o
// plano, o cadastro e a faixa de aviso, e mostra o WhatsApp.

import {
  cadastrar, carregarMensalidade, conferirCupomMensal, cupomDaURL, kitDaURL, reconhecer, tokenDaURL,
} from "./api.js";
import { mesclar, pedacos, previaGuardada, valoresDosMarcadores } from "./conteudo.js";
import { MODULOS } from "./dados.js";
import { esquecer, lembrado, lembrar } from "./memoria.js";
import {
  CONFIG_PADRAO, adicionaisDoCliente, alternarAdicional, aplicarCupom, codigoDeCupom, comConfig,
  configDoServidor, criarPlano, dinheiro, escolherPronto, nomeDoModulo, perfil, problemaNoCadastro, resumo,
  tirarCupom,
} from "./plano.js";

const $ = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";
const CHAVE_AVISO = "dumtech.aviso.fechado";

let plano = criarPlano(CONFIG_PADRAO);
let conteudo = mesclar({});
let modo = "teste";
let cliente = null;
let emPrevia = false;
let linhasAntes = new Set();

// ============================================================== abertura ===
// (chamada no fim do arquivo: as funcoes declaradas com const ja existem la)
function iniciar() {
  // o painel abre a pagina com ?previa=1 depois de guardar o rascunho aqui
  if (new URLSearchParams(location.search).has("previa")) {
    const previa = previaGuardada(armazem());
    if (previa) {
      conteudo = mesclar(previa);
      emPrevia = true;
      $("previa").hidden = false;
    }
  }

  ligarTour();
  ligarModos();
  ligarTopo();
  ligarCupom();
  $("formulario").addEventListener("submit", enviar);
  $("nao-sou-eu").addEventListener("click", naoSouEu);
  $("aviso-fechar").addEventListener("click", fecharAviso);

  // 1. PINTA NA HORA: quem o navegador lembra e o kit que veio no link
  cliente = lembrado(armazem());
  const doLink = kitDaURL();
  plano = criarPlano(CONFIG_PADRAO, doLink.length ? doLink : adicionaisDoCliente(cliente));
  desenharTudo();
  if (cliente) aplicarCliente(cliente);

  // 2. DEPOIS, sem pressa: o que o painel definiu e quem chegou pelo Hub
  carregarMensalidade().then((bruto) => {
    const config = configDoServidor(bruto);
    if (!config) return;
    plano = comConfig(plano, config);
    if (!emPrevia) conteudo = mesclar(bruto.conteudo);
    mostrarAviso(bruto.aviso);
    desenharTudo();
    const cupom = codigoDeCupom(cupomDaURL());
    if (cupom) aplicarCodigo(cupom);
  });
  reconhecer(tokenDaURL()).then((doHub) => {
    if (!doHub) return;
    cliente = lembrar(armazem(), doHub) || doHub;
    if (!doLink.length) plano = criarPlano(plano.config, adicionaisDoCliente(cliente, plano.config));
    aplicarCliente(cliente);
    atualizarPlano();
    // tirou o codigo da barra: ele e de uso unico e nao serve para compartilhar
    history.replaceState(null, "", location.pathname + location.hash);
  });
}

function armazem() {
  try { return window.localStorage; } catch { return null; }
}

function desenharTudo() {
  aplicarTextos();
  desenharProntos();
  desenharAdicionais();
  atualizarPlano();
}

// =============================================================== textos ===
const caminho = (objeto, texto) => texto.split(".").reduce((atual, chave) => atual?.[chave], objeto);

/** Texto com marcadores -> nos de texto, com o valor em destaque. Nunca HTML. */
function preencherNo(alvo, texto, valores) {
  alvo.replaceChildren(...pedacos(texto, valores).map((p) => {
    if (p.texto !== undefined) return document.createTextNode(p.texto);
    const destaque = document.createElement("b");
    destaque.textContent = p.valor;
    return destaque;
  }));
}

function aplicarTextos() {
  const valores = valoresDosMarcadores(plano.config);
  for (const alvo of document.querySelectorAll("[data-texto]")) {
    const texto = caminho(conteudo, alvo.dataset.texto);
    if (typeof texto === "string") preencherNo(alvo, texto, valores);
  }
  const lista = (id, itens, montar) => $(id).replaceChildren(...itens.map(montar));
  // o item e flex (o tique + o texto): o texto vai num span so, senao o
  // destaque do marcador vira um terceiro item, com espaco sobrando
  const itemDeLista = (texto) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    preencherNo(span, texto, valores);
    li.append(span);
    return li;
  };
  lista("fatos", conteudo.fatos, itemDeLista);
  lista("inclui", conteudo.inclui, itemDeLista);
  lista("passos", conteudo.passos, (passo) => {
    const li = document.createElement("li");
    const titulo = document.createElement("h3");
    const texto = document.createElement("p");
    preencherNo(titulo, passo.titulo, valores);
    preencherNo(texto, passo.texto, valores);
    li.append(titulo, texto);
    return li;
  });
  lista("duvidas-lista", conteudo.duvidas.itens, (item) => {
    const detalhe = document.createElement("details");
    const pergunta = document.createElement("summary");
    const resposta = document.createElement("p");
    preencherNo(pergunta, item.pergunta, valores);
    preencherNo(resposta, item.resposta, valores);
    detalhe.append(pergunta, resposta);
    return detalhe;
  });
  for (const link of document.querySelectorAll("[data-whatsapp]")) {
    link.href = linkWhatsApp(link.dataset.whatsapp);
  }
  $("rodape-whatsapp").textContent = `WhatsApp ${telefoneLegivel(conteudo.whatsapp)}`;
  $("base-nomes").textContent = listaDeNomes(plano.config.base);
  for (const el of document.querySelectorAll("[data-dias-teste]")) el.textContent = String(plano.config.diasTeste);
}

const linkWhatsApp = (texto = "") =>
  `https://wa.me/${conteudo.whatsapp}${texto ? `?text=${encodeURIComponent(texto)}` : ""}`;

function telefoneLegivel(numero) {
  const d = String(numero).replace(/^55/, "");
  return d.length === 11 ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}` : numero;
}

function listaDeNomes(codigos) {
  const nomes = codigos.map(nomeDoModulo);
  return nomes.length <= 1 ? (nomes[0] ?? "") : `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}`;
}

function icone(codigo) {
  const modulo = MODULOS.find((m) => m.codigo === codigo);
  const svg = document.createElementNS(svgNS, "svg");
  for (const [nome, valor] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "1.9", "stroke-linecap": "round", "stroke-linejoin": "round" })) svg.setAttribute(nome, valor);
  const desenho = document.createElementNS(svgNS, "path");
  desenho.setAttribute("d", modulo?.icone ?? "");
  svg.append(desenho);
  return svg;
}

const corDe = (codigo) => MODULOS.find((m) => m.codigo === codigo)?.cor ?? "#7353f6";

// ======================================================= planos prontos ===
function desenharProntos() {
  const { planos } = plano.config;
  $("prontos").hidden = !planos.length;
  $("prontos-lista").replaceChildren(...planos.map((p) => {
    const cartao = document.createElement("button");
    cartao.type = "button";
    cartao.className = "pronto-cartao";
    cartao.setAttribute("role", "radio");
    cartao.dataset.id = p.id;
    cartao.dataset.destaque = p.destaque ? "sim" : "nao";
    const partes = [];
    if (p.destaque) partes.push(elemento("span", "pronto-selo", "Recomendado"));
    partes.push(elemento("span", "pronto-nome", p.nome));
    if (p.descricao) partes.push(elemento("span", "pronto-descricao", p.descricao));
    const modulos = elemento("span", "pronto-modulos");
    for (const codigo of p.modulos) {
      const etiqueta = elemento("span", "", nomeDoModulo(codigo));
      etiqueta.style.setProperty("--cor", corDe(codigo));
      modulos.append(etiqueta);
    }
    partes.push(modulos);
    const preco = elemento("span", "pronto-preco");
    if (p.precoCheio) preco.append(elemento("s", "", dinheiro(p.precoCheio)));
    preco.append(elemento("b", "", dinheiro(p.preco)), elemento("small", "", "por mês"));
    partes.push(preco);
    if (p.precoCheio) {
      const ate = p.promoAte ? ` até ${p.promoAte.split("-").reverse().join("/")}` : "";
      partes.push(elemento("span", "pronto-promo", `${p.promoRotulo || "Promoção"}${ate}`));
    }
    cartao.append(...partes);
    cartao.addEventListener("click", () => {
      const ja = plano.escolha.tipo === "pronto" && plano.escolha.id === p.id && !plano.cupom;
      plano = ja ? criarPlano(plano.config) : escolherPronto(plano, p.id);
      limparCupom();
      atualizarPlano();
    });
    return cartao;
  }));
}

function elemento(tag, classe = "", texto = "") {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texto) el.textContent = texto;
  return el;
}

// =========================================================== adicionais ===
function desenharAdicionais() {
  $("adicionais-lista").replaceChildren(...plano.config.adicionais.map(({ codigo, preco }) => {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "adicional";
    botao.setAttribute("role", "switch");
    botao.dataset.codigo = codigo;
    botao.style.setProperty("--cor", corDe(codigo));

    const chave = elemento("span", "chave");
    chave.setAttribute("aria-hidden", "true");
    const desenho = elemento("span", "adicional-icone");
    desenho.setAttribute("aria-hidden", "true");
    desenho.append(icone(codigo));
    const texto = elemento("span", "adicional-texto");
    texto.append(elemento("strong", "", nomeDoModulo(codigo)),
                 elemento("small", "", conteudo.modulos?.[codigo]?.frase ?? ""));
    const valor = elemento("span", "adicional-preco",
      `+ ${preco.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

    botao.append(chave, desenho, texto, valor);
    botao.addEventListener("click", () => {
      plano = alternarAdicional(plano, codigo);
      limparCupom();
      atualizarPlano();
    });
    return botao;
  }));
}

// ============================================================== o plano ===
function atualizarPlano() {
  const r = resumo(plano);
  const curto = (valor) => Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  for (const el of document.querySelectorAll('[data-preco="base"]')) el.textContent = dinheiro(plano.config.precoBase);
  $("plano").querySelector(".plano-escolha").dataset.escolha = r.tipo === "montado" ? "montado" : "pronto";

  const escolhidos = r.tipo === "montado" ? r.adicionais : [];
  for (const botao of document.querySelectorAll(".adicional")) {
    botao.setAttribute("aria-checked", String(escolhidos.includes(botao.dataset.codigo)));
  }
  for (const cartao of document.querySelectorAll(".pronto-cartao")) {
    cartao.setAttribute("aria-checked", String(r.tipo === "pronto" && plano.escolha.id === cartao.dataset.id));
  }

  // o cupom de balcao: uma linha para cada coisa; a que acabou de entrar "imprime"
  const agora = new Set(r.linhas.map((l) => l.texto));
  $("cupom-linhas").replaceChildren(...r.linhas.map((linha) => {
    const li = elemento("li", `cupom-linha${linhasAntes.size && !linhasAntes.has(linha.texto) ? " nova" : ""}`);
    if (linha.valor === null) li.classList.add("cupom-linha-cupom");
    li.append(elemento("span", "", linha.texto), elemento("span", "", linha.valor === null ? "" : curto(linha.valor)));
    if (linha.detalhe) li.append(elemento("small", "", linha.detalhe));
    return li;
  }));
  linhasAntes = agora;

  const promo = $("cupom-promo");
  promo.hidden = !r.totalCheio;
  if (r.totalCheio) {
    const ate = r.ate ? ` até ${r.ate.split("-").reverse().join("/")}` : "";
    promo.replaceChildren(elemento("span", "", `${r.rotulo || "Promoção"}${ate}`),
                          elemento("s", "", dinheiro(r.totalCheio)));
  }
  $("cupom-total").textContent = dinheiro(r.total);

  // assinar: com link vai para o cadastro; sem link, WhatsApp
  const assinar = $("assinar-plano");
  if (r.assinavel) {
    assinar.textContent = `Assinar por ${dinheiro(r.total)} por mês`;
    assinar.href = "#comecar";
    assinar.removeAttribute("target");
    assinar.dataset.modo = "assinar";
  } else {
    assinar.textContent = "Assinar pelo WhatsApp";
    assinar.href = linkWhatsApp(`Olá! Quero assinar o DumTech Hub: ${r.nome} (${dinheiro(r.total)} por mês).`);
    assinar.target = "_blank";
    assinar.rel = "noopener";
    delete assinar.dataset.modo;
  }
  atualizarModo();
}

// ================================================================== cupom ==
function ligarCupom() {
  $("cupom-abrir").addEventListener("click", () => {
    $("cupom-form").hidden = false;
    $("cupom-abrir").hidden = true;
    $("cupom-codigo").focus();
  });
  $("cupom-form").addEventListener("submit", (evento) => {
    evento.preventDefault();
    const codigo = codigoDeCupom($("cupom-codigo").value);
    if (!codigo) return avisarCupom("Confira o código: só letras, números e traço.", "erro");
    aplicarCodigo(codigo);
  });
}

async function aplicarCodigo(codigo) {
  $("cupom-form").hidden = false;
  $("cupom-abrir").hidden = true;
  $("cupom-codigo").value = codigo;
  avisarCupom("Conferindo o cupom…");
  const resposta = await conferirCupomMensal(codigo);
  if (!resposta?.ok) return avisarCupom(resposta?.mensagem || "Esse cupom não vale mais.", "erro");
  plano = aplicarCupom(plano, resposta);
  const r = resumo(plano);
  avisarCupom(`Cupom ${r.pedido.cupom} aplicado: ${r.nome} por ${dinheiro(r.total)} por mês.`, "ok", true);
  atualizarPlano();
}

function avisarCupom(texto, tom = "", comTirar = false) {
  const aviso = $("cupom-aviso");
  aviso.dataset.tom = tom;
  aviso.replaceChildren(texto);
  if (comTirar) {
    const tirar = elemento("button", "link-discreto", "Tirar cupom");
    tirar.type = "button";
    tirar.addEventListener("click", () => {
      plano = tirarCupom(plano);
      limparCupom();
      atualizarPlano();
    });
    aviso.append(tirar);
  }
}

/** Mexeu no plano a mao: o cupom sai, e o aviso dele tambem. */
function limparCupom() {
  if ($("cupom-aviso").dataset.tom === "ok") avisarCupom("");
}

// ======================================================== faixa de aviso ==
function mostrarAviso(aviso) {
  const faixa = $("aviso");
  let fechado = "";
  try { fechado = armazem()?.getItem(CHAVE_AVISO) ?? ""; } catch { /* aba anonima */ }
  if (!aviso?.texto || fechado === aviso.id) {
    faixa.hidden = true;
    return;
  }
  faixa.dataset.tom = ["violeta", "verde", "ambar"].includes(aviso.tom) ? aviso.tom : "violeta";
  faixa.dataset.id = aviso.id;
  const texto = $("aviso-texto");
  if (/^(https:\/\/|#)/.test(aviso.link || "")) {
    const link = elemento("a", "", aviso.texto);
    link.href = aviso.link;
    if (aviso.link.startsWith("https://")) {
      link.target = "_blank";
      link.rel = "noopener";
    }
    texto.replaceChildren(link);
  } else {
    texto.replaceChildren(aviso.texto);
  }
  faixa.hidden = false;
}

function fecharAviso() {
  try { armazem()?.setItem(CHAVE_AVISO, $("aviso").dataset.id || ""); } catch { /* aba anonima */ }
  $("aviso").hidden = true;
}

// ============================================================ testar/assinar ==
function ligarModos() {
  // todo link ou botao com data-modo escolhe o modo; o link ainda rola ate o formulario
  document.addEventListener("click", (evento) => {
    const alvo = evento.target.closest("[data-modo]");
    if (!alvo) return;
    modo = alvo.dataset.modo === "assinar" ? "assinar" : "teste";
    atualizarModo();
  });
}

function atualizarModo() {
  const r = resumo(plano);
  for (const botao of document.querySelectorAll(".modos [data-modo]")) {
    botao.setAttribute("aria-checked", String(botao.dataset.modo === modo));
  }
  $("explica-teste").hidden = modo !== "teste";
  $("explica-assinar").hidden = modo !== "assinar";

  const resumoPlano = $("resumo-plano");
  resumoPlano.hidden = modo !== "assinar";
  resumoPlano.replaceChildren(`Seu plano: ${r.nome} · ${dinheiro(r.total)} por mês. `);
  const mudar = elemento("a", "", "Mudar");
  mudar.href = "#plano";
  resumoPlano.append(mudar);

  const enviarBotao = $("enviar");
  if (!enviarBotao.disabled) {
    enviarBotao.textContent = modo === "teste" ? "Receber minha chave"
      : r.assinavel ? "Continuar para o pagamento" : "Enviar e combinar pelo WhatsApp";
  }
}

// ============================================================= o cadastro ==
async function enviar(evento) {
  evento.preventDefault();
  const dados = {
    nome: $("campo-nome").value.trim(),
    email: $("campo-email").value.trim(),
    whatsapp: $("campo-whatsapp").value.trim(),
  };
  const aviso = $("aviso-form");
  const problema = problemaNoCadastro(dados);
  if (problema) {
    aviso.textContent = problema;
    return;
  }
  aviso.textContent = "";

  const { pedido } = resumo(plano);
  const botao = $("enviar");
  botao.disabled = true;
  botao.textContent = "Enviando…";
  const resposta = await cadastrar({ ...dados, ...pedido, assinar: modo === "assinar" });
  botao.disabled = false;
  atualizarModo();

  if (!resposta.ok) {
    aviso.textContent = resposta.mensagem;
    return;
  }
  // da proxima vez a pagina ja sabe o nome (o tipo so vem pelo Hub)
  lembrar(armazem(), { nome: dados.nome, email: dados.email, produtos: [], tipo: cliente?.tipo || "" });
  mostrarPronto(dados.email, resposta);
}

function mostrarPronto(email, resposta) {
  $("formulario").hidden = true;
  const pronto = $("pronto");
  pronto.hidden = false;

  const assinando = modo === "assinar";
  $("pronto-titulo").textContent = assinando && resposta.link
    ? "Falta só o pagamento." : "Pronto! Confira o seu e-mail.";
  $("pronto-texto").textContent = assinando && resposta.link
    ? `Mandamos a sua chave para ${email}, e você já pode instalar e usar. Para assinar, conclua o pagamento na página da InfinitePay.`
    : `Mandamos a chave e o link para baixar o programa para ${email}. Se não aparecer em alguns minutos, olhe também a caixa de spam.`;

  const acoes = $("pronto-acoes");
  acoes.replaceChildren();
  if (assinando && resposta.link) {
    acoes.append(botaoLink("Continuar para o pagamento", resposta.link, "botao-primario", true));
  } else if (assinando) {
    $("pronto-texto").textContent += " Para assinar, a gente vai chamar você no WhatsApp para combinar o pagamento.";
    acoes.append(botaoLink("Chamar a DumTech agora", linkWhatsApp(`Olá! Acabei de pedir a assinatura do DumTech Hub (${email}).`),
                           "botao-whatsapp", true));
  }
  acoes.append(botaoLink("Baixar o DumTech Hub", "baixar/", assinando ? "botao-claro" : "botao-primario"));
  pronto.focus();
}

function botaoLink(texto, href, classe, foraDaPagina = false) {
  const link = document.createElement("a");
  link.className = `botao botao-grande botao-largo ${classe}`;
  link.textContent = texto;
  link.href = href;
  if (foraDaPagina) {
    link.target = "_blank";
    link.rel = "noopener";
  }
  return link;
}

// ====================================================== quem chegou pelo Hub ==
function aplicarCliente(quem) {
  const primeiro = String(quem.nome || "").trim().split(/\s+/)[0];
  if (quem.nome) $("campo-nome").value ||= quem.nome;
  if (quem.email) $("campo-email").value ||= quem.email;

  const tipo = perfil(quem);
  if (tipo === "novo") return; // so lembrado pelo navegador: o formulario ja vem preenchido

  $("saudacao").hidden = false;
  $("hero-acoes").hidden = true;
  $("hero-nota").hidden = true;
  $("saudacao-titulo").textContent = primeiro ? `Olá, ${primeiro}!` : "Olá!";
  const acoes = $("saudacao-acoes");
  acoes.replaceChildren();

  if (tipo === "vitalicio") {
    document.body.classList.add("vitalicio");
    $("saudacao-texto").textContent =
      "A sua licença DumTech é vitalícia: ela continua sua para sempre, sem mensalidade, e as atualizações " +
      "seguem chegando. Quer mais um módulo? Chame a gente no WhatsApp, que a gente libera na mesma chave.";
    acoes.append(
      botaoCurto("Falar com a DumTech", linkWhatsApp(
        `Olá! Sou cliente da DumTech${quem.email ? ` (${quem.email})` : ""} e quero adicionar um módulo.`), "botao-whatsapp", true),
      botaoCurto("Baixar o DumTech Hub", "baixar/", "botao-claro"),
    );
    return;
  }

  document.body.classList.remove("vitalicio");
  modo = "assinar";
  $("saudacao-texto").textContent = quem.tipo === "assinatura"
    ? "Aqui você muda o seu plano: escolha um plano pronto ou ligue e desligue os adicionais, e assine o plano novo. A sua chave continua a mesma."
    : "Gostou do teste? Escolha o seu plano e assine. A sua chave continua a mesma e nada do que você lançou se perde.";
  acoes.append(botaoCurto(quem.tipo === "assinatura" ? "Mudar meu plano" : "Escolher meu plano", "#plano", "botao-primario"));
}

function botaoCurto(texto, href, classe, foraDaPagina = false) {
  const link = botaoLink(texto, href, classe, foraDaPagina);
  link.classList.remove("botao-largo", "botao-grande");
  return link;
}

function naoSouEu() {
  esquecer(armazem());
  location.href = location.pathname;
}

// ================================================================= o tour ==
function ligarTour() {
  const abas = [...document.querySelectorAll('.tour-abas [role="tab"]')];
  const imagem = $("tour-imagem");
  const tela = $("tour-tela");
  const suave = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const escolher = (aba, focar = false) => {
    for (const outra of abas) {
      const ativa = outra === aba;
      outra.setAttribute("aria-selected", String(ativa));
      outra.tabIndex = ativa ? 0 : -1;
    }
    tela.setAttribute("aria-labelledby", aba.id);
    if (focar) aba.focus();
    if (imagem.getAttribute("src") === aba.dataset.imagem) return;
    const trocar = () => {
      imagem.src = aba.dataset.imagem;
      imagem.alt = aba.dataset.alt;
      imagem.removeAttribute("data-trocando");
    };
    if (!suave) return trocar();
    imagem.dataset.trocando = "";
    setTimeout(trocar, 160);
  };

  abas.forEach((aba, indice) => {
    aba.tabIndex = indice === 0 ? 0 : -1;
    aba.addEventListener("click", () => escolher(aba));
    aba.addEventListener("keydown", (evento) => {
      const passo = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[evento.key];
      if (!passo) return;
      evento.preventDefault();
      escolher(abas[(indice + passo + abas.length) % abas.length], true);
    });
  });
  // a proxima imagem ja vem baixada: trocar de aba nao pisca em branco
  for (const aba of abas) new Image().src = aba.dataset.imagem;
}

// ================================================================== topo ===
function ligarTopo() {
  const topo = $("topo");
  const marcar = () => topo.setAttribute("data-rolou", window.scrollY > 8 ? "sim" : "nao");
  window.addEventListener("scroll", marcar, { passive: true });
  marcar();
}

iniciar();
