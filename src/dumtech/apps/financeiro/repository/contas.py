"""Contas: onde o dinheiro esta, e como ele anda de uma para outra.

Saldo = saldo inicial + baixas de receita - baixas de despesa + transferencias
recebidas - enviadas. Transferencia **nao** e receita nem despesa: sacar do
banco para o caixa nao pode inflar o resultado do mes.
"""

from __future__ import annotations

from ..models import (
    CAIXA,
    CONTA_LABEL,
    Conta,
    FinanceiroError,
    Transferencia,
    hoje_iso,
    ler_data,
)
from .comum import agora, dinheiro

SELECT_CONTA = """
    SELECT c.*, c.saldo_inicial
        + COALESCE((
            SELECT SUM(CASE WHEN l.tipo = 'receita' THEN b.valor ELSE -b.valor END)
            FROM baixas b JOIN lancamentos l ON l.id = b.lancamento_id
            WHERE b.conta_id = c.id
        ), 0)
        + COALESCE((SELECT SUM(t.valor) FROM transferencias t WHERE t.destino_id = c.id), 0)
        - COALESCE((SELECT SUM(t.valor) FROM transferencias t WHERE t.origem_id = c.id), 0)
        AS saldo
    FROM contas c
"""

SELECT_TRANSFERENCIA = """
    SELECT t.*, COALESCE(o.nome, '') AS origem_nome,
                COALESCE(d.nome, '') AS destino_nome
    FROM transferencias t
    LEFT JOIN contas o ON o.id = t.origem_id
    LEFT JOIN contas d ON d.id = t.destino_id
"""


class ContasMixin:
    """Parte do FinanceiroRepository que responde 'quanto eu tenho, e onde?'."""

    # ------------------------------------------------------------------ leitura
    def listar_contas(self, incluir_inativas: bool = False) -> list[Conta]:
        sql = SELECT_CONTA
        if not incluir_inativas:
            sql += " WHERE c.ativo = 1"
        sql += " ORDER BY c.ativo DESC, c.nome COLLATE NOCASE"
        return [Conta.from_row(row) for row in self.db.query(sql)]

    def obter_conta(self, conta_id: int) -> Conta | None:
        row = self.db.query_one(f"{SELECT_CONTA} WHERE c.id = ?", (conta_id,))
        return Conta.from_row(row) if row else None

    def saldo_total(self) -> float:
        return dinheiro(sum(conta.saldo for conta in self.listar_contas()))

    def conta_padrao(self) -> Conta | None:
        """A conta sugerida nas baixas: a primeira ativa, caixa na frente."""
        contas = self.listar_contas()
        if not contas:
            return None
        return next((c for c in contas if c.tipo == CAIXA), contas[0])

    # ------------------------------------------------------------------ escrita
    def criar_conta(self, conta: Conta) -> Conta:
        self._validar_conta(conta)
        momento = agora()
        try:
            cursor = self.db.execute(
                """
                INSERT INTO contas (nome, tipo, saldo_inicial, observacoes, ativo, criado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conta.nome.strip(),
                    conta.tipo,
                    dinheiro(conta.saldo_inicial),
                    conta.observacoes.strip(),
                    1 if conta.ativo else 0,
                    momento,
                ),
            )
        except Exception as erro:  # nome repetido cai no indice UNIQUE
            raise self._erro_de_nome(conta, erro) from erro
        conta.id = int(cursor.lastrowid)
        conta.criado_em = momento
        return conta

    def atualizar_conta(self, conta: Conta) -> Conta:
        if conta.id is None:
            raise FinanceiroError("Conta sem identificacao.")
        self._validar_conta(conta)
        try:
            self.db.execute(
                """
                UPDATE contas SET nome = ?, tipo = ?, saldo_inicial = ?,
                                  observacoes = ?, ativo = ?
                WHERE id = ?
                """,
                (
                    conta.nome.strip(),
                    conta.tipo,
                    dinheiro(conta.saldo_inicial),
                    conta.observacoes.strip(),
                    1 if conta.ativo else 0,
                    conta.id,
                ),
            )
        except Exception as erro:
            raise self._erro_de_nome(conta, erro) from erro
        return conta

    def inativar_conta(self, conta_id: int) -> None:
        self.db.execute("UPDATE contas SET ativo = 0 WHERE id = ?", (conta_id,))

    def reativar_conta(self, conta_id: int) -> None:
        self.db.execute("UPDATE contas SET ativo = 1 WHERE id = ?", (conta_id,))

    def excluir_conta(self, conta_id: int) -> None:
        """Conta com movimento nao some: vira inativa, como o produto no Estoque."""
        if self._tem_movimento(conta_id):
            raise FinanceiroError(
                "Esta conta ja tem movimento. Use 'Inativar' para tira-la da lista "
                "sem perder o historico."
            )
        self.db.execute("DELETE FROM contas WHERE id = ?", (conta_id,))

    # ------------------------------------------------------------ transferencia
    def transferir(
        self,
        origem_id: int,
        destino_id: int,
        valor: float,
        data: str = "",
        observacao: str = "",
    ) -> Transferencia:
        valor = dinheiro(valor)
        if valor <= 0:
            raise FinanceiroError("O valor da transferencia precisa ser maior que zero.")
        if origem_id == destino_id:
            raise FinanceiroError("Escolha duas contas diferentes.")

        origem = self.obter_conta(origem_id)
        destino = self.obter_conta(destino_id)
        if origem is None or destino is None:
            raise FinanceiroError("Escolha as contas de origem e destino.")

        data = data or hoje_iso()
        if ler_data(data) is None:
            raise FinanceiroError("Data da transferencia invalida.")

        momento = agora()
        cursor = self.db.execute(
            """
            INSERT INTO transferencias (origem_id, destino_id, data, valor,
                                        observacao, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (origem_id, destino_id, data, valor, observacao.strip(), momento),
        )
        return Transferencia(
            id=int(cursor.lastrowid),
            origem_id=origem_id,
            destino_id=destino_id,
            data=data,
            valor=valor,
            observacao=observacao.strip(),
            criado_em=momento,
            origem_nome=origem.nome,
            destino_nome=destino.nome,
        )

    def listar_transferencias(self, limite: int = 50) -> list[Transferencia]:
        return [
            Transferencia.from_row(row)
            for row in self.db.query(
                f"{SELECT_TRANSFERENCIA} ORDER BY date(t.data) DESC, t.id DESC LIMIT ?",
                (int(limite),),
            )
        ]

    def excluir_transferencia(self, transferencia_id: int) -> None:
        self.db.execute("DELETE FROM transferencias WHERE id = ?", (transferencia_id,))

    # ------------------------------------------------------------------ interno
    def _tem_movimento(self, conta_id: int) -> bool:
        return bool(
            self.db.scalar("SELECT COUNT(*) FROM baixas WHERE conta_id = ?", (conta_id,))
            or self.db.scalar(
                "SELECT COUNT(*) FROM transferencias WHERE origem_id = ? OR destino_id = ?",
                (conta_id, conta_id),
            )
        )

    @staticmethod
    def _validar_conta(conta: Conta) -> None:
        if not conta.nome.strip():
            raise FinanceiroError("Informe o nome da conta.")
        if conta.tipo not in CONTA_LABEL:
            raise FinanceiroError("Escolha o tipo da conta (caixa, banco ou cartao).")

    @staticmethod
    def _erro_de_nome(conta: Conta, erro: Exception) -> Exception:
        if "UNIQUE" in str(erro):
            return FinanceiroError(f"Ja existe uma conta chamada '{conta.nome.strip()}'.")
        return erro
