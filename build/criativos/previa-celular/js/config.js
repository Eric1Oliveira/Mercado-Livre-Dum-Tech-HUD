// Configuracao da landing page da DumTech.
//
// Este e o UNICO arquivo que voce precisa mexer para publicar.

export const CONFIG = {
  // Servidor de licencas (o mesmo do Hub). A chave "anon" e publica por
  // natureza: ela nao le tabela nenhuma, so executa as funcoes liberadas.
  SUPABASE_URL: "https://kpiyhhmtteojqxhhmcyr.supabase.co/rest/v1",
  SUPABASE_ANON:
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtwaXloaG10dGVvanF4aGhtY3lyIiwicm9sZSI6ImFub24i" +
    "LCJpYXQiOjE3ODc1NTAxMzUsImV4cCI6MjEwMzEyNjEzNX0." +
    "kOvM-Pvau3Es0QD6161LLV3isA4Y7UKWCaKoKnjhQic",

  // O WhatsApp que recebe os kits montados (55 + DDD + numero).
  // Vazio = o site nao abre o WhatsApp; ele so confirma o pedido na tela.
  WHATSAPP: "5511978042160",

  // Quanto tempo o resumo do kit fica na tela antes de voltar ao inicio (ms).
  TEMPO_CONFIRMACAO: 12000,
};

// Em desenvolvimento da para apontar para outro servidor pela URL:
//   index.html?api=http://127.0.0.1:54999/rest/v1
// SO servidor neste computador. Sem a trava, um link
// "...?api=https://servidor-do-golpista" faria a pagina entregar nome, e-mail e
// telefone de quem monta o kit a um estranho (e mostrar precos inventados).
const api = new URLSearchParams(location.search).get("api");
if (api && servidorLocal(api)) CONFIG.SUPABASE_URL = api;

function servidorLocal(endereco) {
  try {
    return ["127.0.0.1", "localhost", "[::1]"].includes(new URL(endereco).hostname);
  } catch {
    return false;
  }
}
