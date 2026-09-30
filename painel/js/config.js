// Configuracao do painel administrativo da DumTech.
//
// Este e o unico arquivo que muda entre um ambiente e outro.

export const CONFIG = {
  // endereco do projeto (SEM /rest/v1: o painel usa /auth e /rest)
  SUPABASE_URL: "https://kpiyhhmtteojqxhhmcyr.supabase.co",

  // A chave "anon" e publica por natureza. Ela sozinha nao ve NADA: as tabelas
  // so respondem para quem esta logado E esta na tabela `administradores`.
  SUPABASE_ANON:
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtwaXloaG10dGVvanF4aGhtY3lyIiwicm9sZSI6ImFub24i" +
    "LCJpYXQiOjE3ODc1NTAxMzUsImV4cCI6MjEwMzEyNjEzNX0." +
    "kOvM-Pvau3Es0QD6161LLV3isA4Y7UKWCaKoKnjhQic",

  // quantos dias as telas de uso olham para tras
  JANELA_DIAS: 30,

  // o que vai na mensagem da chave (WhatsApp / e-mail). Trocou de endereco
  // (dominio proprio)? E so aqui - e em landingpage/js/config.js e core/loja.py.
  // a loja: o link de cupom e o de kit saem daqui
  LOJA_URL: "https://dumtechsolution.com",
  DOWNLOAD_URL: "https://dumtechsolution.com/baixar/",
  // o guia em PDF que vai ANEXADO na mensagem da venda do Mercado Livre
  GUIA_PDF_URL: "https://dumtechsolution.com/guia/Guia-DumTech-Hub.pdf",
  SUPORTE: "WhatsApp (11) 97804-2160",
};

// Em desenvolvimento da para apontar para outro servidor pela URL:
//   index.html?api=http://127.0.0.1:54999
// SO servidor neste computador. Sem a trava, bastava mandar ao administrador um
// link "...?api=https://servidor-do-golpista": a tela de entrada seria a de
// sempre, e o e-mail e a SENHA iriam para o estranho.
const api = new URLSearchParams(location.search).get("api");
if (api && servidorLocal(api)) CONFIG.SUPABASE_URL = api.replace(/\/+$/, "");

function servidorLocal(endereco) {
  try {
    return ["127.0.0.1", "localhost", "[::1]"].includes(new URL(endereco).hostname);
  } catch {
    return false;
  }
}
