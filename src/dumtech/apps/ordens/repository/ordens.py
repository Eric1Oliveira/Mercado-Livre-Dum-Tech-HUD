"""A ordem em si: ler, gravar, apagar."""

from __future__ import annotations

from datetime import date

from ..models import (
    EM_ANDAMENTO,
    ENTREGUE,
    FINALIZADAS,
    Ordem,
    OrdemError,
)
from .comum import agora, dinheiro

CAMPOS = """
    numero, cliente, telefone, equipamento, defeito, diagnostico, servico,
    valor, status, tecnico, aberta_em, prazo, concluida_em, observacoes,
    acessorios, condicao, senha, aprovado_em, aprovado_por, entregue_em,
    garantia_dias, desconto
"""


class OrdensMixin:
    """Parte do OrdensRepository que cuida do cadastro da ordem."""

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        status: str = "",
        tecnico: str = "",
        somente_abertas: bool = False,
        na_garantia: bool = False,
        limite: int = 500,
    ) -> list[Ordem]:
        sql = "SELECT * FROM ordens WHERE 1 = 1"
        params: list = []
        if busca.strip():
            sql += (" AND (numero LIKE ? OR cliente LIKE ? OR equipamento LIKE ?"
                    " OR defeito LIKE ? OR tecnico LIKE ? OR telefone LIKE ?)")
            alvo = f"%{busca.strip()}%"
            params += [alvo] * 6
        if status:
            sql += " AND status = ?"
            params.append(status)
        if tecnico.strip():
            sql += " AND tecnico = ?"
            params.append(tecnico.strip())
        if somente_abertas:
            marcadores = ", ".join("?" for _ in EM_ANDAMENTO)
            sql += f" AND status IN ({marcadores})"
            params += list(EM_ANDAMENTO)
        if na_garantia:
            # garantia corre a partir da entrega
            sql += (" AND status = ? AND garantia_dias > 0 AND TRIM(entregue_em) <> ''"
                    " AND date(entregue_em, '+' || garantia_dias || ' days') >= date(?)")
            params += [ENTREGUE, date.today().isoformat()]

        marcadores = ", ".join("?" for _ in FINALIZADAS)
        sql += f" ORDER BY (status IN ({marcadores})), date(aberta_em) DESC, id DESC LIMIT ?"
        params += list(FINALIZADAS) + [int(limite)]

        ordens = [Ordem.from_row(row) for row in self.db.query(sql, params)]
        for ordem in ordens:
            ordem.itens = self.itens_de(ordem.id)
        return ordens

    def obter(self, ordem_id: int) -> Ordem | None:
        row = self.db.query_one("SELECT * FROM ordens WHERE id = ?", (ordem_id,))
        if row is None:
            return None
        ordem = Ordem.from_row(row)
        ordem.itens = self.itens_de(ordem.id)
        ordem.historico = self.historico_de(ordem.id)
        return ordem

    def proximo_numero(self) -> str:
        """OS-2026-0001. Continua da maior numeracao ja usada no ano."""
        ano = date.today().year
        prefixo = f"OS-{ano}-"
        maior = 0
        for row in self.db.query(
            "SELECT numero FROM ordens WHERE numero LIKE ?", (f"{prefixo}%",)
        ):
            sufixo = str(row["numero"])[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:04d}"

    def acessorios_usados(self, limite: int = 12) -> list[str]:
        """O que ESTA casa costuma receber junto - aprendido do uso.

        Nenhuma lista de fabrica serve a todos: a oficina mecanica recebe
        "estepe" e "documento"; o estudio, "cabo de audio"; o chaveiro, nada.
        Em vez de escolher um ramo pelo cliente, a tela oferece o que ele ja
        escreveu antes, e so cai na lista de fabrica enquanto nao ha historico.
        """
        contagem: dict[str, int] = {}
        for row in self.db.query(
            "SELECT acessorios FROM ordens WHERE TRIM(acessorios) <> '' "
            "ORDER BY id DESC LIMIT 400"
        ):
            for linha in str(row["acessorios"]).splitlines():
                nome = linha.strip()
                if nome:
                    chave = nome.lower()
                    contagem[chave] = contagem.get(chave, 0) + 1
        mais_usados = sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
        return [nome.capitalize() for nome, _ in mais_usados[:limite]]

    def equipamentos(self, limite: int = 60) -> list[str]:
        """Itens ja atendidos, para sugerir enquanto se digita."""
        return [row["equipamento"] for row in self.db.query(
            "SELECT equipamento, MAX(id) AS ultimo FROM ordens "
            "WHERE TRIM(equipamento) <> '' GROUP BY equipamento COLLATE NOCASE "
            "ORDER BY ultimo DESC LIMIT ?", (int(limite),)
        )]

    def tecnicos(self) -> list[str]:
        """Quem ja apareceu como responsavel, para sugerir enquanto se digita."""
        return [row["tecnico"] for row in self.db.query(
            "SELECT DISTINCT tecnico FROM ordens WHERE TRIM(tecnico) <> ''"
            " ORDER BY tecnico COLLATE NOCASE"
        )]

    # ------------------------------------------------------------------ escrita
    def salvar(self, ordem: Ordem) -> Ordem:
        self._validar(ordem)
        momento = agora()
        nova = ordem.id is None

        # com itens, o total vem deles; sem itens, vale o valor digitado
        if ordem.itens:
            ordem.valor = ordem.total
        else:
            ordem.valor = dinheiro(ordem.valor)

        valores = (
            ordem.numero.strip(), ordem.cliente.strip(), ordem.telefone.strip(),
            ordem.equipamento.strip(), ordem.defeito.strip(), ordem.diagnostico.strip(),
            ordem.servico.strip(), ordem.valor, ordem.status,
            ordem.tecnico.strip(), ordem.aberta_em, ordem.prazo or "",
            ordem.concluida_em, ordem.observacoes.strip(),
            ordem.acessorios.strip(), ordem.condicao.strip(), ordem.senha.strip(),
            ordem.aprovado_em, ordem.aprovado_por.strip(), ordem.entregue_em,
            int(ordem.garantia_dias or 0), dinheiro(ordem.desconto),
        )
        if nova:
            colunas = ", ".join(campo.strip() for campo in CAMPOS.split(","))
            marcadores = ", ".join("?" for _ in valores)
            cursor = self.db.execute(
                f"INSERT INTO ordens ({colunas}, criado_em) VALUES ({marcadores}, ?)",
                valores + (momento,),
            )
            ordem.id = int(cursor.lastrowid)
            ordem.criado_em = momento
        else:
            atribuicoes = ", ".join(f"{campo.strip()} = ?" for campo in CAMPOS.split(","))
            self.db.execute(
                f"UPDATE ordens SET {atribuicoes} WHERE id = ?", valores + (ordem.id,)
            )

        self._gravar_itens(ordem)
        if nova:
            self.registrar_evento(ordem.id, ordem.status, "Ordem aberta")
            ordem.historico = self.historico_de(ordem.id)
        return ordem

    def excluir(self, ordem_id: int) -> None:
        ordem = self.obter(ordem_id)
        # entregue e historico do cliente: para desfazer, cancele
        if ordem is not None and ordem.status == ENTREGUE:
            raise OrdemError(
                f"A ordem {ordem.numero} ja foi entregue e nao pode ser apagada. "
                "Cancele a ordem para manter o historico."
            )
        self.db.execute("DELETE FROM ordens WHERE id = ?", (ordem_id,))

    # ------------------------------------------------------------------ regras
    def _validar(self, ordem: Ordem) -> None:
        if not ordem.numero.strip():
            raise OrdemError("Informe o numero da ordem.")
        if not ordem.cliente.strip():
            raise OrdemError("Informe o cliente da ordem.")
        # Um dos dois basta: a lavanderia escreve o pedido e nao tem
        # "equipamento"; a assistencia identifica o aparelho e as vezes so
        # anota o defeito depois. Exigir os dois era exigir texto inventado.
        if not (ordem.equipamento.strip() or ordem.defeito.strip()):
            raise OrdemError(
                "Diga o que foi pedido (ou qual item entrou) para abrir a ordem."
            )
        if dinheiro(ordem.valor) < 0:
            raise OrdemError("O valor nao pode ser negativo.")
        if int(ordem.garantia_dias or 0) < 0:
            raise OrdemError("A garantia nao pode ser negativa.")
        if ordem.itens and dinheiro(ordem.desconto) > ordem.subtotal:
            raise OrdemError("O desconto nao pode ser maior que o total dos itens.")
        repetido = self.db.query_one(
            "SELECT id FROM ordens WHERE numero = ? AND id IS NOT ?",
            (ordem.numero.strip(), ordem.id),
        )
        if repetido is not None:
            raise OrdemError(f"Ja existe uma ordem com o numero {ordem.numero}.")
