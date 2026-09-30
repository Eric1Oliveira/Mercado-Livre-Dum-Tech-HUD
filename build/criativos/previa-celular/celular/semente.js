// Previa do anuncio: o ultimo resumo, como o celular guardaria.
try {
  localStorage.setItem("dumtech.tema", "claro");
  localStorage.setItem("dumtech.celular.acesso", "previa");
  localStorage.setItem("dumtech.celular.computador", "0");
  localStorage.setItem("dumtech.celular.ultimo", "{\"ok\": true, \"cliente\": \"Studio Bella\", \"modulos\": [\"AGENDA\", \"CLIENTES\", \"ORCAMENTOS\"], \"espelhos\": [{\"computador\": \"Computador da loja\", \"atualizado_em\": \"2026-09-27T15:15:25+00:00\", \"dados\": {\"formato\": 1, \"empresa\": \"Studio Bella\", \"versao_hub\": \"1.4.0\", \"gerado_em\": \"2026-09-27T15:15:25+00:00\", \"secoes\": [{\"app\": \"AGENDA\", \"titulo\": \"Agenda\", \"cartoes\": [{\"rotulo\": \"Hoje\", \"valor\": \"4\", \"detalhe\": \"11 na semana\", \"tom\": \"\"}, {\"rotulo\": \"Sem fechar\", \"valor\": \"9\", \"detalhe\": \"compromissos que j\u00e1 passaram\", \"tom\": \"aviso\"}], \"listas\": [{\"titulo\": \"Hoje\", \"linhas\": [{\"texto\": \"Escova + hidratacao\", \"detalhe\": \"Juliana Prado\", \"valor\": \"09:00 as 10:30\", \"tom\": \"\"}, {\"texto\": \"Mechas + matizacao\", \"detalhe\": \"Fernanda Rocha\", \"valor\": \"11:00 as 14:00\", \"tom\": \"\"}, {\"texto\": \"Corte feminino\", \"detalhe\": \"Camila Duarte\", \"valor\": \"15:00 as 16:00\", \"tom\": \"\"}, {\"texto\": \"Unhas em gel\", \"detalhe\": \"Renata Alves\", \"valor\": \"16:30 as 18:00\", \"tom\": \"\"}], \"vazio\": \"Nada marcado para hoje.\"}, {\"titulo\": \"Pr\u00f3ximos\", \"linhas\": [], \"vazio\": \"\"}], \"peso\": 50}, {\"app\": \"ORCAMENTOS\", \"titulo\": \"Or\u00e7amentos\", \"cartoes\": [{\"rotulo\": \"Esperando resposta\", \"valor\": \"2\", \"detalhe\": \"R$ 2.030,00\", \"tom\": \"\"}, {\"rotulo\": \"Aprovados no m\u00eas\", \"valor\": \"1\", \"detalhe\": \"R$ 410,00\", \"tom\": \"ok\"}, {\"rotulo\": \"Convers\u00e3o\", \"valor\": \"50%\", \"detalhe\": \"das propostas respondidas\", \"tom\": \"\"}], \"listas\": [{\"titulo\": \"Vencendo\", \"linhas\": [], \"vazio\": \"Nenhuma proposta vencendo.\"}, {\"titulo\": \"Esperando resposta\", \"linhas\": [{\"texto\": \"Aline Barros\", \"detalhe\": \"ORC-2026-0001 \u00b7 h\u00e1 3 dias\", \"valor\": \"R$ 1.390,00\", \"tom\": \"\"}], \"vazio\": \"\"}], \"peso\": 40}, {\"app\": \"CLIENTES\", \"titulo\": \"Clientes\", \"cartoes\": [{\"rotulo\": \"Clientes ativos\", \"valor\": \"6\", \"detalhe\": \"6 novos no m\u00eas\", \"tom\": \"\"}], \"listas\": [{\"titulo\": \"Aniversariantes do m\u00eas\", \"linhas\": [{\"texto\": \"Fernanda Rocha\", \"detalhe\": [2, 9], \"valor\": \"\", \"tom\": \"\"}], \"vazio\": \"Ningu\u00e9m faz anivers\u00e1rio este m\u00eas.\"}], \"peso\": 30}]}}]}");
} catch (e) {}

// Sem rede de proposito: ver o comentario do modulo (armadilha 3).
window.fetch = function () {
  return Promise.reject(new TypeError("previa: sem rede de proposito"));
};

// A falha de rede escreve "Sem conexao - tentando de novo" no topo. E verdade
// nesta previa e mentira no celular de quem comprou, que esta pareado: o
// anuncio nao pode carimbar um defeito que o produto nao tem. Aqui o subtitulo
// volta a dizer o que o cliente ve de verdade.
addEventListener("load", function () {
  setInterval(function () {
    var q = document.getElementById("quando");
    if (q && /conex|tentando|offline/i.test(q.textContent || "")) {
      q.textContent = "atualizado agora mesmo";
    }
  }, 120);
});
