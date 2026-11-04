"""O que acompanha a ordem: checklist, fotos e a assinatura do cliente.

Nada disso muda o dinheiro nem o estoque. Serve para provar o que aconteceu: como
o item chegou, o que foi conferido e quem recebeu.
"""

from __future__ import annotations

from ..models import FotoOS, OrdemError, TarefaOS
from .comum import agora


class AnexosMixin:
    """Parte do OrdensRepository que guarda as provas do servico."""

    # --------------------------------------------------------------- checklist
    def checklist_de(self, ordem_id: int) -> list[TarefaOS]:
        return [
            TarefaOS(id=row["id"], texto=row["texto"], feito=bool(row["feito"]))
            for row in self.db.query(
                "SELECT * FROM os_checklist WHERE ordem_id = ? ORDER BY id", (ordem_id,)
            )
        ]

    def adicionar_tarefa(self, ordem_id: int, texto: str) -> TarefaOS:
        texto = texto.strip()
        if not texto:
            raise OrdemError("Escreva o que precisa ser conferido.")
        cursor = self.db.execute(
            "INSERT INTO os_checklist (ordem_id, texto) VALUES (?, ?)", (ordem_id, texto)
        )
        return TarefaOS(id=int(cursor.lastrowid), texto=texto)

    def marcar_tarefa(self, tarefa_id: int, feito: bool) -> None:
        self.db.execute("UPDATE os_checklist SET feito = ? WHERE id = ?",
                        (int(feito), tarefa_id))

    def remover_tarefa(self, tarefa_id: int) -> None:
        self.db.execute("DELETE FROM os_checklist WHERE id = ?", (tarefa_id,))

    def tarefas_usadas(self, limite: int = 30) -> list[str]:
        """O que esta casa costuma conferir, para sugerir enquanto se digita."""
        return [row["texto"] for row in self.db.query(
            "SELECT texto, COUNT(*) AS vezes FROM os_checklist GROUP BY texto COLLATE NOCASE"
            " ORDER BY vezes DESC, texto LIMIT ?", (int(limite),),
        )]

    # ------------------------------------------------------------------- fotos
    def fotos_de(self, ordem_id: int) -> list[FotoOS]:
        return [
            FotoOS(id=row["id"], imagem=bytes(row["imagem"]), criado_em=row["criado_em"])
            for row in self.db.query(
                "SELECT * FROM os_fotos WHERE ordem_id = ? ORDER BY id DESC", (ordem_id,)
            )
        ]

    def adicionar_foto(self, ordem_id: int, imagem: bytes) -> None:
        self.db.execute(
            "INSERT INTO os_fotos (ordem_id, imagem, criado_em) VALUES (?, ?, ?)",
            (ordem_id, imagem, agora()),
        )

    def remover_foto(self, foto_id: int) -> None:
        self.db.execute("DELETE FROM os_fotos WHERE id = ?", (foto_id,))

    # -------------------------------------------------------------- assinatura
    def assinar(self, ordem_id: int, imagem: bytes | None) -> None:
        self.db.execute(
            "UPDATE ordens SET assinatura = ?, assinado_em = ? WHERE id = ?",
            (imagem, agora() if imagem else "", ordem_id),
        )

    def assinatura_de(self, ordem_id: int) -> bytes | None:
        linha = self.db.query_one("SELECT assinatura FROM ordens WHERE id = ?", (ordem_id,))
        return bytes(linha["assinatura"]) if linha and linha["assinatura"] else None
