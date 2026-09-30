// Tempo real: ouve um canal do Supabase Realtime e avisa quando o banco muda.
//
// O aviso NAO traz dado nenhum - so "a tabela X mudou". Quem ouve busca de novo
// pelo caminho de sempre (a funcao publica no site, as policies no painel).
// Assim o tempo real deixa a tela rapida sem abrir porta nova no banco.
//
// Sem biblioteca: o protocolo e o do Phoenix (JSON por WebSocket) e cabe aqui.
// Caiu a conexao? Reconecta sozinho, esperando um pouco mais a cada tentativa -
// e, ao voltar, avisa "mudou" uma vez, porque algo pode ter mudado no escuro.
//
// COPIA IDENTICA em painel/js/tempo-real.js: as duas paginas sao publicadas
// separadas e sem build. Mudou uma, mude a outra (os testes moram na landing).

export const BATIDA_MS = 25_000;
export const ESPERAS_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

/** wss://<projeto>.supabase.co/realtime/v1/websocket?apikey=...&vsn=1.0.0 */
export function enderecoDoSocket(supabaseUrl, chave) {
  const base = new URL(supabaseUrl);
  const protocolo = base.protocol === "http:" ? "ws:" : "wss:";
  return `${protocolo}//${base.host}/realtime/v1/websocket` +
    `?apikey=${encodeURIComponent(chave)}&vsn=1.0.0`;
}

/** A mensagem que entra no canal. Canal privado exige o token da sessao. */
export function pedidoDeEntrada(topico, { privado = false, token = "", ref = "1" } = {}) {
  return {
    topic: `realtime:${topico}`,
    event: "phx_join",
    ref,
    join_ref: ref,
    payload: {
      config: {
        broadcast: { ack: false, self: false },
        presence: { enabled: false },
        postgres_changes: [],
        private: privado,
      },
      access_token: token,
    },
  };
}

/**
 * O que uma mensagem do servidor significa para quem ouve:
 *   {tipo: "mudou", tabela, op} | {tipo: "entrou"} | {tipo: "recusado", motivo}
 *   | {tipo: "caiu", motivo} | null (nada a fazer: batida, outro canal...)
 */
export function interpretar(mensagem, topico) {
  if (!mensagem || mensagem.topic !== `realtime:${topico}`) return null;
  const carga = mensagem.payload || {};

  switch (mensagem.event) {
    case "broadcast":
      return { tipo: "mudou", tabela: String(carga.payload?.tabela || ""), op: String(carga.payload?.op || "") };
    case "phx_reply":
      if (carga.status === "ok") return { tipo: "entrou" };
      return { tipo: "recusado", motivo: String(carga.response?.reason || carga.status || "") };
    case "phx_error":
    case "phx_close":
      return { tipo: "caiu", motivo: mensagem.event };
    case "system":
      // ex.: o token da sessao venceu - o servidor tira a gente do canal
      return carga.status === "error" ? { tipo: "caiu", motivo: String(carga.message || "") } : null;
    default:
      return null;
  }
}

/**
 * Ouve um canal ate `parar()`.
 *   aoMudar({tabela, op})  - chamado a cada aviso (e uma vez ao reconectar)
 *   aoEstado("conectando" | "ao-vivo" | "fora")
 *   token()                - async; so canal privado precisa (padrao: a chave)
 */
export function ouvir({
  url, chave, topico, privado = false,
  token = async () => chave,
  aoMudar = () => {}, aoEstado = () => {},
  criarSocket = (endereco) => new WebSocket(endereco),
  esperas = ESPERAS_MS,
}) {
  let socket = null;
  let batida = null;
  let espera = null;
  let tentativas = 0;
  let ref = 0;
  let parado = false;
  let jaEntrou = false;

  const avisarEstado = (estado) => {
    try { aoEstado(estado); } catch { /* a tela nao derruba a conexao */ }
  };
  const enviar = (alvo, mensagem) => {
    if (alvo?.readyState === 1) alvo.send(JSON.stringify(mensagem));
  };

  async function conectar() {
    if (parado) return;
    avisarEstado("conectando");

    let acesso = chave;
    try {
      acesso = (await token()) || chave;
    } catch {
      /* sem sessao: tenta assim mesmo; o servidor recusa e a gente espera */
    }
    if (parado) return;

    let meu;
    try {
      meu = criarSocket(enderecoDoSocket(url, chave));
    } catch {
      reagendar();
      return;
    }
    socket = meu;

    meu.onopen = () => {
      enviar(meu, pedidoDeEntrada(topico, { privado, token: acesso, ref: String(++ref) }));
      clearInterval(batida);
      batida = setInterval(() => {
        enviar(meu, { topic: "phoenix", event: "heartbeat", payload: {}, ref: String(++ref) });
      }, BATIDA_MS);
    };

    meu.onmessage = (evento) => {
      let mensagem;
      try {
        mensagem = JSON.parse(evento.data);
      } catch {
        return;
      }
      const sentido = interpretar(mensagem, topico);
      if (!sentido) return;

      if (sentido.tipo === "entrou") {
        tentativas = 0;
        avisarEstado("ao-vivo");
        // voltou depois de cair: o que mudou enquanto estava fora nao chegou
        if (jaEntrou) chamar({ tabela: "", op: "reconectou" });
        jaEntrou = true;
      } else if (sentido.tipo === "mudou") {
        chamar(sentido);
      } else {
        meu.close(); // recusado ou caiu: o onclose reagenda
      }
    };

    meu.onclose = () => {
      if (meu !== socket) return;
      clearInterval(batida);
      socket = null;
      avisarEstado("fora");
      reagendar();
    };
    meu.onerror = () => { /* o onclose vem logo em seguida */ };
  }

  function chamar(sentido) {
    try {
      aoMudar({ tabela: sentido.tabela, op: sentido.op });
    } catch (erro) {
      console.error(erro);
    }
  }

  function reagendar() {
    if (parado) return;
    clearTimeout(espera);
    const ms = esperas[Math.min(tentativas, esperas.length - 1)];
    tentativas += 1;
    espera = setTimeout(conectar, ms);
  }

  conectar();

  return {
    parar() {
      parado = true;
      clearTimeout(espera);
      clearInterval(batida);
      const antigo = socket;
      socket = null;
      try { antigo?.close(); } catch { /* ja estava fechado */ }
      avisarEstado("fora");
    },
    /** Fecha e abre de novo (ex.: o token da sessao foi renovado). */
    reconectar() {
      try { socket?.close(); } catch { /* o onclose reagenda */ }
    },
  };
}
