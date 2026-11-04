"""Importar e exportar CSV.

Sem isso ninguem consegue comecar a usar o programa com um catalogo que ja
existe. A importacao roda em dois tempos: primeiro `prever_importacao` mostra o
que vai acontecer, depois `importar` executa - o usuario nunca e surpreendido.
"""

from __future__ import annotations

import csv
import io
import re

from ..models import UNIDADE_PADRAO, UNIDADES, EstoqueError, PreviaImportacao, Produto
from .comum import dinheiro, quantidade

#: cabecalho do arquivo exportado, que e tambem o formato aceito na importacao
COLUNAS_PRODUTOS = [
    "codigo",
    "nome",
    "codigo_barras",
    "categoria",
    "unidade",
    "quantidade",
    "estoque_minimo",
    "estoque_maximo",
    "preco_custo",
    "preco_venda",
    "fornecedor",
    "localizacao",
    "descricao",
]

COLUNAS_MOVIMENTACOES = [
    "data",
    "tipo",
    "codigo",
    "produto",
    "quantidade",
    "saldo_atual",
    "custo_unitario",
    "fornecedor",
    "documento",
    "observacao",
]

#: nomes alternativos aceitos - planilha de cliente raramente vem com o nosso
SINONIMOS = {
    "cod": "codigo",
    "codigo interno": "codigo",
    "sku": "codigo",
    "produto": "nome",
    "descricao do produto": "nome",
    "ean": "codigo_barras",
    "codigo de barras": "codigo_barras",
    "barras": "codigo_barras",
    "un": "unidade",
    "unid": "unidade",
    "qtd": "quantidade",
    "quantidade atual": "quantidade",
    "saldo": "quantidade",
    "estoque": "quantidade",
    "minimo": "estoque_minimo",
    "estoque min": "estoque_minimo",
    "maximo": "estoque_maximo",
    "estoque max": "estoque_maximo",
    "custo": "preco_custo",
    "preco de custo": "preco_custo",
    "venda": "preco_venda",
    "preco de venda": "preco_venda",
    "preco": "preco_venda",
    "local": "localizacao",
    "prateleira": "localizacao",
}


def _normalizar(cabecalho: str) -> str:
    limpo = (cabecalho or "").strip().lower().replace("_", " ")
    limpo = "".join(
        c for c in limpo.replace("ç", "c").replace("ã", "a").replace("é", "e")
        .replace("í", "i").replace("ó", "o").replace("ú", "u").replace("á", "a")
    )
    return SINONIMOS.get(limpo, limpo.replace(" ", "_"))


def _numero(valor: str) -> float:
    """Le numero do jeito que a planilha trouxer.

    Com os dois separadores, o ultimo e o dos centavos: "1.234,56" e "1,234.56".
    So com ponto em grupos de tres, e milhar: "1.500" sao mil e quinhentos, e
    nao um e meio. O que este programa exporta sai com virgula decimal, para
    "12,345" (quilos) voltar igual.
    """
    texto = (valor or "").replace("R$", "").replace(" ", "").strip()
    if not texto:
        return 0.0
    virgula, ponto = texto.rfind(","), texto.rfind(".")
    if virgula >= 0 and ponto >= 0:
        milhar, decimal = (".", ",") if virgula > ponto else (",", ".")
        texto = texto.replace(milhar, "").replace(decimal, ".")
    elif virgula >= 0:
        texto = texto.replace(",", "") if texto.count(",") > 1 else texto.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError as exc:
        raise ValueError(f"'{valor}' não é um número") from exc


def _texto(numero: float) -> str:
    """Numero com virgula decimal: o Excel daqui le, e `_numero` le de volta."""
    return str(numero).replace(".", ",")


class PlanilhaMixin:
    """Parte do EstoqueRepository que fala com planilhas."""

    # --------------------------------------------------------------- exportar
    def exportar_produtos_csv(self, incluir_inativos: bool = False) -> str:
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(COLUNAS_PRODUTOS)
        for p in self.listar(incluir_inativos=incluir_inativos):
            escritor.writerow([
                p.codigo, p.nome, p.codigo_barras, p.categoria, p.unidade,
                _texto(p.quantidade), _texto(p.estoque_minimo), _texto(p.estoque_maximo),
                _texto(p.preco_custo), _texto(p.preco_venda), p.fornecedor, p.localizacao,
                p.descricao,
            ])
        return saida.getvalue()

    def exportar_movimentacoes_csv(self, limite: int = 5000) -> str:
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(COLUNAS_MOVIMENTACOES)
        for m in self.listar_movimentacoes(limite=limite):
            escritor.writerow([
                m.criado_em, m.tipo_label, m.produto_codigo, m.produto_nome,
                m.quantidade, m.saldo_atual, m.custo_unitario, m.fornecedor,
                m.documento, m.observacao,
            ])
        return saida.getvalue()

    # --------------------------------------------------------------- importar
    def prever_importacao(self, texto: str) -> PreviaImportacao:
        """Le a planilha e diz o que faria, sem gravar nada."""
        previa = PreviaImportacao()
        vistos: set[str] = set()

        for linha_numero, bruto in self._ler_linhas(texto):
            try:
                produto = self._produto_da_linha(bruto)
            except ValueError as erro:
                previa.recusados.append((linha_numero, str(erro)))
                continue

            chave = produto.codigo.lower()
            if chave in vistos:
                previa.recusados.append(
                    (linha_numero, f"código '{produto.codigo}' repetido na planilha")
                )
                continue
            vistos.add(chave)

            existente = self.buscar_por_codigo(produto.codigo)
            if existente is None:
                previa.criar.append(produto)
            else:
                produto.id = existente.id
                previa.atualizar.append(produto)
        return previa

    def importar(self, texto: str, atualizar_existentes: bool = True) -> tuple[int, int]:
        """Aplica a planilha. Devolve (criados, atualizados)."""
        previa = self.prever_importacao(texto)
        if not previa.total_valido:
            raise EstoqueError(
                "Nenhuma linha válida encontrada. Confira se a planilha tem as "
                "colunas 'código' e 'nome'."
            )

        # tudo ou nada: a planilha pela metade e a pior das duas
        criados = atualizados = 0
        with self.db.transaction():
            for produto in previa.criar:
                self.criar(produto)
                criados += 1

            if atualizar_existentes:
                for produto in previa.atualizar:
                    atual = self.obter(produto.id)
                    # a quantidade nao vem da planilha numa atualizacao: quem manda
                    # no saldo e o historico de movimentacoes, nao um arquivo
                    produto.quantidade = atual.quantidade
                    self.atualizar(produto)
                    atualizados += 1
        return criados, atualizados

    # ------------------------------------------------------------------ leitura
    @staticmethod
    def _ler_linhas(texto: str):
        if not texto.strip():
            raise EstoqueError("O arquivo está vazio.")
        amostra = texto[:2048]
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)

        try:
            cabecalho = [_normalizar(c) for c in next(leitor)]
        except StopIteration as exc:
            raise EstoqueError("O arquivo está vazio.") from exc
        if "codigo" not in cabecalho or "nome" not in cabecalho:
            raise EstoqueError(
                "A planilha precisa ter pelo menos as colunas 'código' e 'nome'."
            )

        for numero, linha in enumerate(leitor, start=2):
            if not any(campo.strip() for campo in linha):
                continue
            yield numero, dict(zip(cabecalho, linha))

    @staticmethod
    def _produto_da_linha(bruto: dict[str, str]) -> Produto:
        codigo = (bruto.get("codigo") or "").strip()
        nome = (bruto.get("nome") or "").strip()
        if not codigo:
            raise ValueError("sem codigo")
        if not nome:
            raise ValueError("sem nome")

        unidade = (bruto.get("unidade") or UNIDADE_PADRAO).upper().strip()
        if unidade not in UNIDADES:
            raise ValueError(f"unidade '{unidade}' desconhecida")

        try:
            return Produto(
                codigo=codigo,
                nome=nome,
                codigo_barras=(bruto.get("codigo_barras") or "").strip(),
                categoria=(bruto.get("categoria") or "").strip(),
                unidade=unidade,
                quantidade=quantidade(_numero(bruto.get("quantidade", ""))),
                estoque_minimo=quantidade(_numero(bruto.get("estoque_minimo", ""))),
                estoque_maximo=quantidade(_numero(bruto.get("estoque_maximo", ""))),
                preco_custo=dinheiro(_numero(bruto.get("preco_custo", ""))),
                preco_venda=dinheiro(_numero(bruto.get("preco_venda", ""))),
                fornecedor=(bruto.get("fornecedor") or "").strip(),
                localizacao=(bruto.get("localizacao") or "").strip(),
                descricao=(bruto.get("descricao") or "").strip(),
            )
        except ValueError as erro:
            raise ValueError(str(erro)) from erro
