"""Os numeros com contexto: ritmo do dia, tendencia e o que mais sai.

Feito para rodar a cada poucos segundos (o resumo do celular, na tela do
computador da loja): o banco soma dia a dia (SQLite faz isso em C) e venda a
venda so se le nos poucos dias em que a HORA importa - hoje e os dias que se
comparam com ele.

Mesmo assim, numa loja de 100 vendas por dia a conta leva ~40 ms - e o
celular pergunta a cada 5 s, na tela de quem esta vendendo. Entao o resultado
fica guardado e so e refeito quando o banco foi gravado (o WAL do SQLite muda
a cada commit) ou quando o minuto vira (o "ate agora" anda com o relogio).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from ..models import CANCELADA, PENDENTE, DiaDeVenda, IndicadoresVendas, MaisVendido
from .comum import dinheiro

#: dias de historia que a tendencia usa: 30 na tela + os 30 de antes, para comparar
DIAS_DE_HISTORIA = 60

#: as janelas que o celular compara ("7 dias", "30 dias"): o dia que corresponde
#: a hoje em cada janela anterior precisa ser cortado no mesmo horario
JANELAS = (7, 30)

#: o total de cada dia; o de cada venda como o modelo calcula (item arredondado,
#: menos o desconto, nunca negativo)
_POR_DIA = (
    "SELECT dia, COUNT(*) AS vendas, SUM(total) AS total FROM ("
    " SELECT v.data AS dia,"
    "  MAX(COALESCE(SUM(ROUND(i.quantidade * i.valor_unitario, 2)), 0) - v.desconto, 0) AS total"
    " FROM vendas v LEFT JOIN venda_itens i ON i.venda_id = v.id"
    " WHERE v.status <> ? AND v.data >= ? GROUP BY v.id"
    ") GROUP BY dia"
)

#: venda a venda, com a hora - so nos dias em que a hora importa
_COM_HORA = (
    "SELECT v.data, v.criado_em, v.desconto,"
    " COALESCE((SELECT SUM(ROUND(i.quantidade * i.valor_unitario, 2))"
    "           FROM venda_itens i WHERE i.venda_id = v.id), 0) AS subtotal"
    " FROM vendas v WHERE v.status <> ? AND v.data IN ({})"
)

_PENDENTES = (
    "SELECT v.desconto,"
    " COALESCE((SELECT SUM(ROUND(i.quantidade * i.valor_unitario, 2))"
    "           FROM venda_itens i WHERE i.venda_id = v.id), 0) AS subtotal"
    " FROM vendas v WHERE v.status = ?"
)

_POR_FORMA = (
    "SELECT p.forma AS forma, SUM(p.valor) AS valor FROM pagamentos p"
    " JOIN vendas v ON v.id = p.venda_id"
    " WHERE v.status <> ? AND v.data >= ? AND v.data <= ? AND p.valor > 0"
    " GROUP BY p.forma"
)

#: venda de antes do PDV nao tem linha de pagamento: a forma mora na venda
_SEM_PAGAMENTO = (
    "SELECT COALESCE(NULLIF(TRIM(v.forma_pagamento), ''), 'Nao informado') AS forma, v.desconto,"
    " COALESCE((SELECT SUM(ROUND(i.quantidade * i.valor_unitario, 2))"
    "           FROM venda_itens i WHERE i.venda_id = v.id), 0) AS subtotal"
    " FROM vendas v WHERE v.status <> ? AND v.data >= ? AND v.data <= ?"
    " AND NOT EXISTS (SELECT 1 FROM pagamentos p WHERE p.venda_id = v.id)"
)

#: o mesmo produto do Estoque e uma linha so, mesmo que o nome tenha mudado
_MAIS_VENDIDOS = (
    "SELECT MAX(i.descricao) AS descricao, SUM(i.quantidade) AS quantidade,"
    " SUM(ROUND(i.quantidade * i.valor_unitario, 2)) AS valor,"
    " MAX(i.unidade) AS unidade, MAX(i.casas) AS casas"
    " FROM venda_itens i JOIN vendas v ON v.id = i.venda_id"
    " WHERE v.status <> ? AND v.data >= ? AND v.data <= ?"
    " GROUP BY CASE WHEN i.produto_id > 0 THEN 'p' || i.produto_id"
    "               ELSE 'd' || LOWER(TRIM(i.descricao)) END"
    " ORDER BY valor DESC LIMIT ?"
)


def _total(row) -> float:
    return max(dinheiro(float(row["subtotal"] or 0) - float(row["desconto"] or 0)), 0.0)


def _momento(row) -> datetime | None:
    """Quando a venda fechou - so se foi no proprio dia dela."""
    criado = str(row["criado_em"] or "")
    if criado[:10] != str(row["data"] or "")[:10]:
        return None  # data trocada na mao: o dia vale, a hora nao se sabe
    try:
        return datetime.fromisoformat(criado[:19])
    except ValueError:
        return None


#: o ultimo calculo de cada banco (um por arquivo: nao cresce)
_GUARDADOS: dict[str, tuple[tuple, IndicadoresVendas]] = {}


def _assinatura(banco: Path) -> tuple:
    """Muda a cada gravacao: no modo WAL todo commit mexe no -wal (ou no banco)."""
    partes: list[int] = []
    for arquivo in (banco, banco.with_name(banco.name + "-wal")):
        try:
            info = arquivo.stat()
            partes += [info.st_mtime_ns, info.st_size]
        except OSError:
            partes += [0, 0]
    return tuple(partes)


def _mesmo_dia_no_mes_passado(hoje: date) -> tuple[date, date]:
    """(dia 1, o mesmo dia) do mes passado - 31 vira o ultimo dia que existir."""
    ultimo = hoje.replace(day=1) - timedelta(days=1)
    return ultimo.replace(day=1), ultimo.replace(day=min(hoje.day, ultimo.day))


class IndicadoresMixin:
    """Parte do VendasRepository que compara."""

    def indicadores(self, agora: datetime | None = None, limite_ranking: int = 5) -> IndicadoresVendas:
        """Os indicadores de agora - refeitos so quando o banco ou o minuto mudam.

        Quem passa o relogio (`agora`) quer a conta feita na hora: sem guardar.
        """
        if agora is not None:
            return self._calcular(agora.replace(microsecond=0), limite_ranking)
        agora = datetime.now().replace(second=0, microsecond=0)
        banco = Path(self.db.path)
        chave = (agora, int(limite_ranking), _assinatura(banco))
        guardado = _GUARDADOS.get(str(banco))
        if guardado is not None and guardado[0] == chave:
            return guardado[1]
        resultado = self._calcular(agora, limite_ranking)
        _GUARDADOS[str(banco)] = (chave, resultado)
        return resultado

    def _calcular(self, agora: datetime, limite_ranking: int) -> IndicadoresVendas:
        hoje = agora.date()
        mes_passado, mesmo_dia = _mesmo_dia_no_mes_passado(hoje)
        desde = min(hoje - timedelta(days=DIAS_DE_HISTORIA - 1), mes_passado)
        base = hoje - timedelta(days=7)
        relogio = agora.time()

        r = IndicadoresVendas(agora=agora)
        for row in self.db.query(_POR_DIA, (CANCELADA, desde.isoformat())):
            chave = str(row["dia"] or "")[:10]
            try:
                dia = date.fromisoformat(chave)
            except ValueError:
                continue  # data torta no banco: nao entra na conta do celular
            total, vendas = dinheiro(row["total"]), int(row["vendas"] or 0)
            registro = r.dias.setdefault(chave, DiaDeVenda())
            registro.total = dinheiro(registro.total + total)
            registro.ate_agora = registro.total
            registro.vendas += vendas
            if (dia.year, dia.month) == (hoje.year, hoje.month):
                r.mes = dinheiro(r.mes + total)
                r.vendas_mes += vendas
            elif mes_passado <= dia <= mesmo_dia:
                r.mes_anterior = dinheiro(r.mes_anterior + total)
                r.vendas_mes_anterior += vendas

        # a hora so importa em hoje e nos dias que se comparam com ele
        com_hora = sorted({hoje, base, *(hoje - timedelta(days=n) for n in JANELAS)})
        for dia in com_hora:
            if dia.isoformat() in r.dias:
                r.dias[dia.isoformat()].ate_agora = 0.0
        sql = _COM_HORA.format(", ".join("?" * len(com_hora)))
        for row in self.db.query(sql, (CANCELADA, *(d.isoformat() for d in com_hora))):
            total = _total(row)
            registro = r.dias.get(str(row["data"] or "")[:10])
            if registro is None:
                continue
            momento = _momento(row)
            # sem hora conhecida, conta como venda do comeco do dia
            if momento is None or momento.time() <= relogio:
                registro.ate_agora = dinheiro(registro.ate_agora + total)
            hora = momento.hour if momento is not None else 0
            if str(row["data"])[:10] == hoje.isoformat():
                r.horas_hoje[hora] = dinheiro(r.horas_hoje[hora] + total)
            elif str(row["data"])[:10] == base.isoformat():
                r.horas_base[hora] = dinheiro(r.horas_base[hora] + total)

        pendentes = [_total(row) for row in self.db.query(_PENDENTES, (PENDENTE,))]
        r.pendentes = dinheiro(sum(pendentes))
        r.vendas_pendentes = len(pendentes)

        do_mes = (CANCELADA, hoje.replace(day=1).isoformat(), hoje.isoformat())
        r.mais_vendidos = [
            MaisVendido(
                descricao=str(row["descricao"] or "Sem nome"),
                quantidade=float(row["quantidade"] or 0),
                valor=dinheiro(row["valor"]),
                unidade=str(row["unidade"] or "UN"),
                casas=int(row["casas"] or 0),
            )
            for row in self.db.query(_MAIS_VENDIDOS, (*do_mes, int(limite_ranking)))
        ]

        formas: dict[str, float] = {}
        for row in self.db.query(_POR_FORMA, do_mes):
            formas[row["forma"]] = dinheiro(formas.get(row["forma"], 0.0) + float(row["valor"] or 0))
        for row in self.db.query(_SEM_PAGAMENTO, do_mes):
            formas[row["forma"]] = dinheiro(formas.get(row["forma"], 0.0) + _total(row))
        r.por_forma = sorted(((f, v) for f, v in formas.items() if v > 0), key=lambda par: -par[1])
        return r
