// Os módulos DumTech, do jeito que o painel os desenha.
//
// Cor e ícone saem do MANIFEST de cada aplicativo (src/dumtech/apps/<id>/
// module.py) e de ui/icons.py — o painel usa os mesmos traços do programa.
// Nome e preço vêm do banco; aqui fica só a identidade visual.

export const MODULOS = {
  ESTOQUE: {
    nome: "Estoque", cor: "#8A7BF8",
    icone: "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z M3 7.5 12 12l9-4.5 M12 12v9",
  },
  VENDAS: {
    nome: "Vendas", cor: "#D8574F",
    icone: "M3 4h2.2l2.3 11.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.2L21 8H6 M9.5 20.5h.01 M17.5 20.5h.01",
  },
  FINANCEIRO: {
    nome: "Financeiro", cor: "#2E9E6B",
    icone: "M3 6h18v12H3z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6.5 9.5h.01 M17.5 14.5h.01",
  },
  ORCAMENTOS: {
    nome: "Orçamentos", cor: "#E0902F",
    icone: "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4z M14 3v4h4 M9 12.5h6 M9 16.5h6",
  },
  ORDENS: {
    nome: "Ordem de Serviço", cor: "#4C7EF3",
    icone: "M20.5 6.2a5.5 5.5 0 0 1-7.3 7.3L6 20.7a2 2 0 0 1-2.8-2.8l7.2-7.2a5.5 5.5 0 0 1 7.3-7.3l-3.2 3.2 2.8 2.8 3.2-3.2z",
  },
  CLIENTES: {
    nome: "Clientes", cor: "#2FB6A6",
    icone: "M9 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20a6.5 6.5 0 0 1 13 0 M17 5.2a3.5 3.5 0 0 1 0 6.6 M18 14.4a6.5 6.5 0 0 1 3.5 5.6",
  },
  AGENDA: {
    nome: "Agenda", cor: "#C05FD4",
    icone: "M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M4 10h16 M8.5 3v4 M15.5 3v4 M8 14h.01 M12 14h.01 M16 14h.01",
  },
};

/** Módulo pelo código; produto novo que o painel ainda não conhece vira neutro. */
export function modulo(codigo) {
  const chave = String(codigo || "").toUpperCase();
  return (
    MODULOS[chave] || {
      nome: chave || "—",
      cor: "#75758a",
      icone: "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z",
    }
  );
}

export const cor = (codigo) => modulo(codigo).cor;
