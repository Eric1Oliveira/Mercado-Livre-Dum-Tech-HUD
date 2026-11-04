// Acessos: quem ja tem conta no Hub, loja por loja, e o cartao de contas da ficha.
//
// O painel nunca ve senha: a provisoria nasce no navegador, vai derivada para o
// banco e aparece uma vez, para copiar. O que filtra e conta mora em acessos.js.

import { ler, rpc } from "../api.js";
import {
  FILTROS, avisosDos, derivarSenha, filtrarAcessos, gerarProvisoria, licencasParaExigir, modulosDaEdicao,
  montarAcessos, resumoMigracao,
} from "../acessos.js";
import { numero, relativo } from "../formato.js";
import { modulo } from "../modulos.js";
import { abrirGaveta, recarregar } from "../painel.js";
import { agir, botaoWhatsApp, cartao, chips, confirmar, el, pessoa, pilula, recado, tabela, tile } from "../ui.js";
import { campo, ficha } from "./comercial.js";

let filtroAtual = "todas";

/** O banco responde {ok:false, mensagem} nas recusas de regra: vira erro na tela. */
async function pedir(funcao, parametros) {
  const resposta = await rpc(funcao, parametros);
  if (!resposta?.ok) throw new Error(resposta?.mensagem || "");
  return resposta;
}

const contasDaLoja = (linha) => {
  if (!linha.contas) return "Nenhuma";
  const partes = [];
  if (linha.adms) partes.push(`${numero(linha.adms)} ADM`);
  if (linha.funcionarios) partes.push(`${numero(linha.funcionarios)} funcionário${linha.funcionarios > 1 ? "s" : ""}`);
  return partes.join(" · ") || `${numero(linha.contas)} bloqueada${linha.contas > 1 ? "s" : ""}`;
};

const pilulaDaLoja = (linha) => {
  if (linha.exigirConta && !linha.contas) return pilula("Exigindo conta", "aviso");
  if (linha.exigirConta) return pilula("Com conta · exigida", "ok");
  return linha.contas ? pilula("Com conta", "ok") : pilula("Sem conta");
};

// ================================================================== a tela ===
export async function acessos(alvo) {
  const [clientes, resumo, ativacoes] = await Promise.all([
    ler("painel_clientes", { ordem: "nome.asc" }),
    rpc("dumtech_painel_acessos", {}, { grava: false }),
    ler("ativacoes", { select: "licenca_id,maquina,versao" }),
  ]);
  const linhas = montarAcessos(clientes, resumo || [], ativacoes);
  const totais = resumoMigracao(linhas);
  const alvoDeExigir = licencasParaExigir(linhas);

  const corpo = el("div");
  const desenhar = () => {
    corpo.replaceChildren(
      chips(FILTROS.map((f) => ({ ...f, conta: filtrarAcessos(linhas, f.valor).length })), filtroAtual, (valor) => {
        filtroAtual = valor;
        desenhar();
      }),
      cartao("", tabela(
        ["Loja", "Situação", "Contas", "Último acesso", "Atenção"],
        filtrarAcessos(linhas, filtroAtual),
        (linha) => [
          pessoa(linha.cliente.nome, linha.cliente.email || "sem e-mail"),
          pilulaDaLoja(linha),
          contasDaLoja(linha),
          linha.ultimoAcesso ? relativo(linha.ultimoAcesso) : "—",
          el("div", {}, [
            linha.emailDifere ? el("div", { classe: "sub-linha", texto: "E-mail do ADM diferente do cadastro" }) : null,
            linha.contas && linha.semLogin
              ? el("div", { classe: "sub-linha", texto: `${numero(linha.semLogin)} computador(es) abrem sem login` }) : null,
          ]),
        ],
        { aoClicar: (linha) => ficha(linha.cliente), vazioTexto: "Nenhuma loja neste filtro." },
      )),
    );
  };
  desenhar();

  alvo.append(
    el("div", { classe: "pagina-cabeca" }, [
      el("div", {}, [
        el("h1", { texto: "Acessos" }),
        el("p", { texto: "Quem já criou conta no Hub e quem ainda abre sem login. Nenhuma loja é obrigada " +
                         "a criar conta até você exigir." }),
      ]),
      el("button", {
        classe: "botao botao-fantasma", texto: `Exigir de todas (${numero(alvoDeExigir.length)})`,
        disabled: !alvoDeExigir.length,
        onclick: (e) => {
          if (!confirmar(`Exigir conta de ${alvoDeExigir.length} loja(s)? Ao abrir o Hub, quem não tem conta ` +
                         "vai precisar criar antes de usar. Sem internet, ninguém fica preso.")) return;
          agir(e.target, async () => {
            await pedir("dumtech_painel_exigir_conta", { p_licencas: alvoDeExigir, p_valor: true });
            recarregar();
          }, { feito: "Pronto. O Hub de cada loja recebe em até 2 minutos." });
        },
      }),
    ]),
    el("div", { classe: "tiles" }, [
      tile("Com conta", `${numero(totais.comConta)} de ${numero(totais.total)}`, "lojas com chave"),
      tile("Sem conta", numero(totais.semConta), "ainda abrem como antes"),
      tile("Exigindo", numero(totais.exigindo), "sem o botão Agora não"),
      tile("Abrem sem login", numero(totais.computadoresSemLogin), "computadores em versão antiga, em lojas com conta",
        totais.computadoresSemLogin ? "ruim" : ""),
    ]),
    corpo,
  );
}

// ========================================================= o cartao da ficha ==
/** Contas da loja na ficha do cliente. Sem a migration, a ficha abre sem ele. */
export async function cartaoContas(cliente, { depois }) {
  let dados;
  try {
    dados = await rpc("dumtech_painel_usuarios", { p_licenca: cliente.licenca_id }, { grava: false });
  } catch (erro) {
    if (erro.status !== 404) console.warn("contas da loja", erro);
    return null;
  }
  const usuarios = dados?.usuarios || [];
  const licenciados = (cliente.produtos_codigos || []).map((codigo) => String(codigo).toLowerCase());

  const exigir = el("label", { classe: "pilula", title: "Tira o botão Agora não do convite, nesta loja" }, [
    el("input", {
      type: "checkbox", checked: Boolean(dados?.exigir_conta),
      onchange: (e) => agir(null, async () => {
        await pedir("dumtech_painel_exigir_conta", { p_licencas: [cliente.licenca_id], p_valor: e.target.checked });
        await depois();
      }, { feito: "Pronto. O Hub recebe em até 2 minutos." }),
    }),
    "Exigir conta",
  ]);

  const novo = el("button", {
    classe: "botao botao-fantasma botao-mini", texto: "Nova conta",
    onclick: () => editarConta(cliente, null, licenciados, depois),
  });

  const corpo = usuarios.length
    ? tabela(
      ["Pessoa", "Tipo", "Último acesso", ""],
      usuarios,
      (u) => [
        pessoa(u.nome, [u.login, u.email].filter(Boolean).join(" · ")),
        el("div", {}, [
          pilula(u.papel === "adm" ? "Administrador" : "Funcionário", u.papel === "adm" ? "ok" : ""),
          u.ativo ? null : pilula("Bloqueada", "ruim"),
          u.papel === "adm" && !u.email_confirmado ? el("div", { classe: "sub-linha", texto: "E-mail sem confirmar" }) : null,
        ]),
        u.ultimo_acesso ? `${relativo(u.ultimo_acesso)} · ${u.ultimo_computador || "—"}` : "nunca entrou",
        el("div", { classe: "acoes-linha" }, [
          el("button", { classe: "botao botao-fantasma botao-mini", texto: "Editar",
                         onclick: () => editarConta(cliente, u, licenciados, depois) }),
          el("button", { classe: "botao botao-fantasma botao-mini", texto: "Senha",
                         onclick: (e) => redefinirSenha(e.target, cliente, u, depois) }),
          el("button", {
            classe: "botao botao-fantasma botao-mini", texto: u.ativo ? "Bloquear" : "Desbloquear",
            onclick: (e) => {
              if (u.ativo && !confirmar(`Bloquear ${u.nome}? A pessoa sai do Hub e não entra mais até desbloquear.`)) return;
              agir(e.target, async () => {
                await pedir("dumtech_painel_salvar_usuario", {
                  p_licenca: cliente.licenca_id, p_id: u.id, p_dados: { ...u, ativo: !u.ativo }, p_senha_hash: "",
                });
                await depois();
              }, { feito: u.ativo ? "Conta bloqueada." : "Conta desbloqueada." });
            },
          }),
          el("button", {
            classe: "botao botao-fantasma botao-mini", texto: "Apagar",
            onclick: (e) => {
              if (!confirmar(`Apagar a conta de ${u.nome}? O que a pessoa lançou nos módulos continua lá.`)) return;
              agir(e.target, async () => {
                await pedir("dumtech_painel_apagar_usuario", { p_id: u.id });
                await depois();
              }, { feito: "Conta apagada." });
            },
          }),
        ]),
      ],
    )
    : el("p", { estilo: "color:var(--tinta-media)",
                texto: "Esta loja ainda não criou conta: o Hub abre sem login, com tudo liberado." });

  return cartao("Contas e acessos", corpo, el("div", { classe: "acoes-linha" }, [exigir, novo]));
}

/** A senha ja foi trocada no banco: falhar ao redesenhar nao pode perde-la. */
async function redesenhar(depois) {
  try {
    await depois();
  } catch (erro) {
    console.warn("ficha nao redesenhou", erro);
  }
}

async function redefinirSenha(botao, cliente, usuario, depois) {
  if (!confirmar(`Redefinir a senha de ${usuario.nome}? Quem estiver usando a conta sai na hora.`)) return;
  const senha = gerarProvisoria();
  const feito = await agir(botao, async () => {
    await pedir("dumtech_painel_senha_provisoria", { p_id: usuario.id, p_senha_hash: await derivarSenha(senha) });
    await redesenhar(depois);
    return true;
  }, { feito: "" });
  if (!feito) return;

  mostrarAcesso(cliente, usuario.nome, usuario.login, senha);
}

/** A senha aparece aqui e em mais lugar nenhum: o banco so guarda o hash. */
function mostrarAcesso(cliente, nome, login, senha) {
  const texto = `Seu acesso ao DumTech Hub\nLogin: ${login}\nSenha: ${senha}\n` +
                "No próximo acesso, o Hub pede para você criar a sua senha.";
  abrirGaveta({
    acima: "Senha provisória", titulo: nome,
    conteudo: cartao("", [
      el("p", { estilo: "color:var(--tinta-media);margin-bottom:12px",
                texto: "Copie agora: esta senha não aparece de novo." }),
      el("div", { classe: "dados" }, [
        el("div", {}, [el("span", { texto: "Login " }), el("code", { texto: login })]),
        el("div", {}, [el("span", { texto: "Senha " }), el("code", { texto: senha })]),
      ]),
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Copiar acesso",
          onclick: async () => {
            await navigator.clipboard.writeText(texto);
            recado("Acesso copiado.", "ok");
          },
        }),
        cliente.telefone ? botaoWhatsApp(cliente.telefone, texto) : null,
        el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: () => ficha(cliente) }),
      ]),
    ]),
  });
}

function editarConta(cliente, usuario, licenciados, depois) {
  const nome = el("input", { value: usuario?.nome || "" });
  const login = el("input", { value: usuario?.login || "", autocomplete: "off", spellcheck: "false" });
  const email = el("input", { type: "email", value: usuario?.email || "" });
  const papel = el("select", {}, [
    el("option", { value: "funcionario", texto: "Funcionário" }),
    el("option", { value: "adm", texto: "Administrador" }),
  ]);
  papel.value = usuario?.papel || "funcionario";

  const marcados = new Set(usuario?.modulos || []);
  const caixas = licenciados.map((app) => {
    const caixa = el("input", { type: "checkbox", checked: marcados.has(app) });
    return { app, caixa, rotulo: el("label", { classe: "pilula" }, [caixa, modulo(app).nome]) };
  });
  // um <label> dentro de outro confunde o clique: aqui o campo e uma <div>
  const blocoModulos = el("div", { classe: "campo" }, [
    el("span", { texto: "Módulos que a pessoa vê" }),
    el("div", { classe: "acoes-linha" }, caixas.map((c) => c.rotulo)),
    el("small", { classe: "dica", texto: "Ela recebe os avisos destes módulos. Para ajustar aviso por aviso, o ADM faz pelo Hub." }),
  ]);
  const ajustar = () => { blocoModulos.hidden = papel.value === "adm"; };
  papel.addEventListener("change", ajustar);
  ajustar();

  abrirGaveta({
    acima: usuario ? "Editar conta" : "Nova conta", titulo: usuario?.nome || cliente.nome,
    conteudo: cartao("", [
      campo("Nome", nome), campo("Login", login, "Sem espaços e sem acentos."),
      campo("E-mail", email, "Obrigatório para administrador: é por ele que a senha é recuperada."),
      campo("Tipo", papel), blocoModulos,
      el("div", { classe: "acoes-linha", estilo: "margin-top:14px" }, [
        el("button", {
          classe: "botao botao-primario", texto: "Salvar",
          onclick: (e) => {
            const provisoria = usuario ? "" : gerarProvisoria();
            agir(e.target, async () => {
              const modulos = papel.value === "adm" ? [] : modulosDaEdicao(
                caixas.filter((c) => c.caixa.checked).map((c) => c.app), usuario?.modulos, licenciados);
              // na edicao os avisos ficam como o ADM deixou: so entra ou sai o que acompanha o modulo
              const antigos = (usuario?.avisos || []).filter((a) => avisosDos(modulos).includes(a));
              const novos = avisosDos(modulos.filter((m) => !(usuario?.modulos || []).includes(m)));
              await pedir("dumtech_painel_salvar_usuario", {
                p_licenca: cliente.licenca_id, p_id: usuario?.id || null,
                p_dados: {
                  nome: nome.value, login: login.value, email: email.value, papel: papel.value,
                  modulos, avisos: [...new Set([...antigos, ...novos])], ativo: usuario?.ativo ?? true,
                },
                p_senha_hash: provisoria ? await derivarSenha(provisoria) : "",
              });
              await redesenhar(depois);
              if (provisoria) mostrarAcesso(cliente, nome.value, login.value.trim().toLowerCase(), provisoria);
            }, { feito: "Conta salva." });
          },
        }),
        el("button", { classe: "botao botao-fantasma", texto: "Voltar", onclick: () => ficha(cliente) }),
      ]),
    ]),
  });
}

