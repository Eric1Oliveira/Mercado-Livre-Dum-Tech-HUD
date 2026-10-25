// Kits: montar, precificar e tirar de venda os pacotes de modulos.
//
// O que a tela garante:
//   * o preco pode ser dado em R$ ou em % de desconto sobre os avulsos;
//   * a economia aparece enquanto se digita;
//   * kit que sai mais caro que os avulsos nao e salvo a venda - a loja nunca
//     o aplicaria (licao do "Gestao" a R$ 699 contra R$ 199,60 avulsos);
//   * kit que ja foi vendido nao e apagado: sai de linha. Quem comprou continua
//     com a licenca intacta - a venda guarda uma fotografia do que levou.
//
// Salvou aqui, a loja muda na hora (o site ouve o catalogo em tempo real).

import { apagar, atualizar, inserir, ler } from "../api.js";
import { dinheiro, numero } from "../formato.js";
import { avaliar, codigoDoNome, precoComDesconto } from "../kits.js";
import { desde, porKit, totais } from "../relatorio.js";
import { modulo } from "../modulos.js";
import { abrirGaveta, fecharGaveta, recarregar } from "../painel.js";
import { agir, cartao, confirmar, el, pilula, pilulaModulo, recado, tabela, tile } from "../ui.js";

//: periodo do relatorio (dias; 0 = tudo). Fica entre um redesenho e outro.
let periodo = 30;

export async function kits(alvo) {
  const corte = desde(periodo);
  const [produtos, combos, itens, vendidos, pedidos] = await Promise.all([
    ler("produtos", { ordem: "codigo.asc" }),
    ler("combos", { ordem: "preco.asc" }),
    ler("combo_produtos"),
    ler("licenca_produtos", { select: "combo_id", filtros: { combo_id: "not.is.null" } }),
    ler("pedidos_site", {
      select: "itens,total,subtotal,desconto,cupom,pagamento,pago_valor,criado_em",
      ...(corte ? { filtros: { criado_em: `gte.${corte}` } } : {}),
    }),
  ]);
  const idsDe = (combo) => itens.filter((i) => i.combo_id === combo.id).map((i) => i.produto_id);
  const codigoDe = new Map(produtos.map((p) => [p.id, p.codigo]));
  const vendas = new Map();
  for (const v of vendidos) vendas.set(v.combo_id, (vendas.get(v.combo_id) || 0) + 1);

  alvo.append(el("div", { classe: "pagina-cabeca" }, [
    el("div", {}, [
      el("h1", { texto: "Kits" }),
      el("p", { texto: "Quando o cliente marca na loja os módulos de um kit, o preço do kit entra sozinho. " +
                        "Salvou aqui, o site muda na hora." }),
    ]),
    el("div", { classe: "ferramentas" }, [
      el("button", {
        classe: "botao botao-primario", texto: "Novo kit",
        onclick: () => editar(null, produtos, [], 0),
      }),
    ]),
  ]));

  alvo.append(desempenho(pedidos, combos, produtos, idsDe));

  alvo.append(cartao("Kits", tabela(
    ["Kit", "Módulos", { texto: "Avulso", numero: true }, { texto: "No kit", numero: true },
     { texto: "Economia", numero: true }, { texto: "Vendidos", numero: true }, "Situação"],
    combos,
    (c) => {
      const ids = idsDe(c);
      const conta = avaliar(produtos, ids, c.preco);
      return [
        el("div", {}, [el("strong", { texto: c.nome }),
                       el("div", { classe: "rodape-entrada", texto: c.ramo ? `${c.codigo} · ramo: ${c.ramo}` : c.codigo })]),
        el("div", { classe: "modulos-lista" }, ids.map((id) => pilulaModulo(codigoDe.get(id)))),
        el("s", { texto: dinheiro(conta.soma) }),
        el("strong", { texto: dinheiro(c.preco) }),
        conta.problema ? "—" : `${dinheiro(conta.economia)} (${conta.porcento}%)`,
        numero(vendas.get(c.id) || 0),
        conta.problema
          ? pilula("Nunca aplicado", "aviso")
          : c.ativo ? pilula("À venda", "ok") : pilula("Fora de linha", "neutro"),
      ];
    },
    {
      aoClicar: (c) => editar(c, produtos, idsDe(c), vendas.get(c.id) || 0),
      vazioTexto: "Nenhum kit ainda. Crie o primeiro em “Novo kit”.",
    }
  )));
}

// ------------------------------------------------------------ desempenho ---
/**
 * Quais kits vendem e que desconto converte. "Pedidos" e quem chegou ate o
 * pagamento; "Vendas" e quem pagou. Conversao baixa com muito pedido quer
 * dizer preco que assusta na hora de pagar.
 */
function desempenho(pedidos, combos, produtos, idsDe) {
  const porCodigo = new Map(combos.map((c) => [c.codigo, c]));
  const linhas = porKit(pedidos);
  const t = totais(pedidos);

  const escolha = el("select", {
    onchange: async (e) => { periodo = Number(e.target.value); await recarregar(); },
  }, [[30, "Últimos 30 dias"], [90, "Últimos 90 dias"], [0, "Desde o começo"]].map(([dias, texto]) =>
    el("option", { value: String(dias), texto, selected: dias === periodo })));

  const cartoes = el("div", { classe: "tiles" }, [
    tile("Pedidos", numero(t.pedidos), "chegaram ao pagamento"),
    tile("Vendas", numero(t.pagos), "pagas"),
    tile("Conversão", `${t.conversao}%`, "vendas ÷ pedidos", t.conversao >= 50 ? "ok" : ""),
    tile("Receita", dinheiro(t.receita), t.pagos ? `ticket médio ${dinheiro(t.ticket)}` : ""),
  ]);

  const tabelaKits = tabela(
    ["Kit", { texto: "Desconto", numero: true }, { texto: "Pedidos", numero: true },
     { texto: "Vendas", numero: true }, { texto: "Conversão", numero: true },
     { texto: "Receita", numero: true }, { texto: "Ticket", numero: true }],
    linhas,
    (l) => {
      const combo = porCodigo.get(l.chave);
      const conta = combo ? avaliar(produtos, idsDe(combo), combo.preco) : null;
      return [
        combo ? combo.nome : l.chave === "AVULSO" ? "Módulos avulsos" : `${l.chave} (fora de linha)`,
        conta && !conta.problema ? `${conta.porcento}%` : "—",
        numero(l.pedidos), numero(l.pagos),
        l.pedidos ? `${l.conversao}%` : "—",
        dinheiro(l.receita), l.pagos ? dinheiro(l.ticket) : "—",
      ];
    },
    { vazioTexto: "Nenhum pedido no período." }
  );

  return cartao("Desempenho", [cartoes, tabelaKits], el("div", { classe: "ferramentas" }, [escolha]));
}

// ------------------------------------------------------------------ editor ---
function editar(combo, produtos, idsIniciais, vendidos) {
  const novo = !combo;
  const escolhidos = new Set(idsIniciais);

  const nome = campo("Nome na loja", combo?.nome || "", { placeholder: "Kit Comércio" });
  const descricao = campo("Frase curta (aparece no cartão da loja)", combo?.descricao || "",
                          { placeholder: "Balcão, estoque e clientes numa chave só" });
  const ramo = campo("Ramo em “Qual é o seu negócio?” (vazio = não aparece lá)", combo?.ramo || "",
                     { placeholder: "Oficina ou assistência técnica" });
  const desconto = campo("Desconto sobre os avulsos (%)", "", { type: "number", min: "0", max: "95", step: "1" });
  const preco = campo("Preço do kit (R$)", combo?.preco ?? "", { type: "number", min: "0", step: "0.01" });
  const ativo = el("input", { type: "checkbox", checked: combo ? combo.ativo : true });
  const conta = el("div", { classe: "nota-kit" });

  const atualizarConta = () => {
    const r = avaliar(produtos, [...escolhidos], Number(preco.valor()));
    conta.replaceChildren(
      el("span", { texto: "Avulso " }), el("s", { texto: dinheiro(r.soma) }),
      el("span", { texto: "  →  no kit " }), el("strong", { texto: dinheiro(r.preco) }),
      r.problema ? "" : el("span", { texto: `  ·  economia de ${dinheiro(r.economia)} (${r.porcento}%)` }),
      r.problema ? el("p", { classe: "nota-alerta", texto: r.problema }) : "",
    );
    return r;
  };
  // % -> R$ (arredonda para ,90); R$ -> mostra o % equivalente
  desconto.entrada.addEventListener("input", () => {
    const r = avaliar(produtos, [...escolhidos], 0);
    preco.entrada.value = precoComDesconto(r.soma, desconto.valor()).toFixed(2);
    atualizarConta();
  });
  preco.entrada.addEventListener("input", () => {
    desconto.entrada.value = String(avaliar(produtos, [...escolhidos], Number(preco.valor())).porcento || "");
    atualizarConta();
  });

  const lista = el("div", { classe: "modulos-lista" }, produtos.filter((p) => p.ativo || escolhidos.has(p.id)).map((p) => {
    const marca = el("input", {
      type: "checkbox", checked: escolhidos.has(p.id),
      onchange: (e) => {
        if (e.target.checked) escolhidos.add(p.id); else escolhidos.delete(p.id);
        // com desconto definido, o preco acompanha a troca de modulos
        if (desconto.valor()) desconto.entrada.dispatchEvent(new Event("input"));
        else atualizarConta();
      },
    });
    return el("label", { classe: "pilula", "data-tom": "neutro", estilo: "gap:7px;cursor:pointer" },
              [marca, modulo(p.codigo).nome]);
  }));
  const inicial = atualizarConta();
  if (!novo && !inicial.problema) desconto.entrada.value = String(inicial.porcento);

  const salvar = (e) => {
    const r = atualizarConta();
    const dados = { nome: nome.valor().trim(), descricao: descricao.valor().trim(),
                    ramo: ramo.valor().trim(), preco: Number(preco.valor()), ativo: ativo.checked };
    if (!dados.nome) return recado("Dê um nome ao kit.", "erro");
    if (r.problema && dados.ativo) return recado(r.problema, "erro");
    const codigo = novo ? codigoDoNome(dados.nome) : combo.codigo;
    if (!codigo) return recado("Use letras no nome do kit.", "erro");

    agir(e.target, async () => {
      let alvo = combo;
      if (novo) {
        const criado = await inserir("combos", { ...dados, codigo });
        alvo = Array.isArray(criado) ? criado[0] : criado;
      } else {
        await atualizar("combos", { id: `eq.${combo.id}` }, dados);
      }
      const antes = new Set(idsIniciais);
      const saindo = [...antes].filter((id) => !escolhidos.has(id));
      const entrando = [...escolhidos].filter((id) => !antes.has(id))
        .map((id) => ({ combo_id: alvo.id, produto_id: id }));
      await Promise.all([
        saindo.length
          ? apagar("combo_produtos", { combo_id: `eq.${alvo.id}`, produto_id: `in.(${saindo.join(",")})` })
          : null,
        entrando.length ? inserir("combo_produtos", entrando) : null,
      ]);
      fecharGaveta();
      await recarregar();
    }, { feito: "Kit salvo. A loja já mostra a mudança." });
  };

  // vendido ou nao, quem comprou nao perde nada: os modulos ficam nas licencas
  // (o banco so solta a marca de "veio do kit"), e o pedido guarda o nome dele
  const tirarDeLinha = (e) => agir(e.target, async () => {
    await atualizar("combos", { id: `eq.${combo.id}` }, { ativo: false });
    fecharGaveta();
    await recarregar();
  }, { feito: "Kit fora de linha. Quem comprou não perde nada." });

  const excluir = (e) => {
    const aviso = vendidos > 0
      ? `O kit “${combo.nome}” já foi vendido ${vendidos} vez(es). Quem comprou não perde nada: os módulos ` +
        "continuam nas licenças e os pedidos guardam o nome do kit.\n\nExcluir mesmo assim? Ele some da loja e do painel."
      : `Excluir o kit “${combo.nome}”? Ele nunca foi vendido.`;
    if (!confirmar(aviso)) return;
    agir(e.target, async () => {
      await apagar("combo_produtos", { combo_id: `eq.${combo.id}` });
      await apagar("combos", { id: `eq.${combo.id}` }, { conferir: true });
      fecharGaveta();
      await recarregar();
    }, { feito: "Kit excluído." });
  };

  abrirGaveta({
    acima: novo ? "Novo kit" : "Kit",
    titulo: novo ? "Montar kit" : combo.nome,
    conteudo: el("div", {}, [
      cartao("", [
        nome.no, descricao.no, ramo.no,
        el("div", { classe: "campo" }, [el("span", { texto: "Módulos do kit" }), lista]),
        el("div", { classe: "linha-campos" }, [desconto.no, preco.no]),
        conta,
        el("label", { classe: "campo", estilo: "flex-direction:row;align-items:center;gap:8px" },
          [ativo, el("span", { texto: "À venda (aparece na loja)" })]),
        el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
          el("button", { classe: "botao botao-primario", texto: novo ? "Criar kit" : "Salvar", onclick: salvar }),
          novo || !vendidos || !combo.ativo ? "" : el("button", { classe: "botao botao-fantasma", texto: "Tirar de linha",
                                                                  onclick: tirarDeLinha }),
          novo ? "" : el("button", { classe: "botao botao-perigo", texto: "Excluir", onclick: excluir }),
          el("button", { classe: "botao botao-fantasma", texto: "Cancelar", onclick: fecharGaveta }),
        ]),
      ]),
      el("p", { classe: "rodape-entrada", estilo: "margin-top:12px",
        texto: "Mudar o kit não muda o que os clientes já compraram. Na loja, quem marcar exatamente estes " +
               "módulos (ou mais) recebe o preço do kit sozinho." }),
    ]),
  });
}

function campo(rotulo, valorInicial, atributos = {}) {
  const entrada = el("input", { ...atributos, value: valorInicial });
  const no = el("label", { classe: "campo" }, [el("span", { texto: rotulo }), entrada]);
  return { no, entrada, valor: () => String(entrada.value ?? "").trim() };
}
