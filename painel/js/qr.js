// O QR Code do segundo fator, pronto para entrar num `<img src=...>`.
//
// POR QUE ISTO EXISTE
//   O Supabase (GoTrue) devolve `totp.qr_code` de formas diferentes conforme a
//   versao: ora o SVG **cru** (`<svg ...>`), ora ja embrulhado em `data:`, com
//   ou sem `charset`. SVG cru dentro de `src` nao desenha nada - e a tela do
//   primeiro login mostrava um icone de imagem quebrada, bem na hora em que a
//   pessoa precisa ler o codigo com o celular.
//
//   Aqui tudo isso vira um endereco que o navegador entende. Se nem assim der
//   (campo vazio, formato novo), devolve "" e quem chama mostra a chave escrita
//   - que cadastra o autenticador do mesmo jeito, digitando.

const PREFIXO_SVG = "data:image/svg+xml";

/** `qr_code` do Supabase -> endereco para o `<img>`. "" quando nao da para desenhar. */
export function imagemDoQr(qr) {
  const texto = String(qr ?? "").trim();
  if (!texto) return "";

  // ja veio como data: (png em base64, por exemplo) - so o SVG precisa de cuidado
  if (texto.startsWith("data:")) {
    if (!texto.startsWith(PREFIXO_SVG)) return texto;
    const virgula = texto.indexOf(",");
    if (virgula < 0) return "";
    const corpo = texto.slice(virgula + 1);
    return svgParaEndereco(corpo.trim().startsWith("<") ? corpo : decodificar(corpo));
  }

  // SVG cru, do jeito que o servidor manda hoje
  if (texto.startsWith("<")) return svgParaEndereco(texto);

  // otpauth://... (ou qualquer novidade): nao e desenho, e quem chama que decide
  return "";
}

/** O `#` das cores precisa ir codificado, senao o navegador corta o desenho ali. */
function svgParaEndereco(svg) {
  const limpo = String(svg || "").trim();
  return limpo ? `${PREFIXO_SVG};charset=utf-8,${encodeURIComponent(limpo)}` : "";
}

function decodificar(texto) {
  try {
    return decodeURIComponent(texto);
  } catch {
    return texto; // veio com % solto: melhor tentar o original do que perder o QR
  }
}
