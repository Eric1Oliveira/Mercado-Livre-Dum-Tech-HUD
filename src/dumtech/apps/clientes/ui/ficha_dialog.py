"""Ficha do cliente: tudo que se sabe sobre ele, num lugar so.

A metade de cima sao os dados; a de baixo e a memoria do atendimento - o que
foi combinado, quando, com quem falou. E o que transforma um cadastro numa
relacao.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....core.contacts import Contato, ContactsStore, ContatoError
from ....ui import format as fmt
from ....ui.theme import Space, apply_window_theme, palette_for
from ....ui.widgets.buttons import Button
from ....ui.widgets.common import Card, IconBadge, Pill, label, repolish, separator


class FichaDialog(QDialog):
    """Consulta rapida do cliente, com as anotacoes datadas."""

    def __init__(
        self,
        store: ContactsStore,
        contato: Contato,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.contato = contato
        self.houve_mudanca = False

        self.setWindowTitle(f"Ficha - {contato.nome}")
        self.setModal(True)
        self.setMinimumSize(720, 620)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(separator())
        raiz.addWidget(self._dados())
        raiz.addWidget(label("Anotacoes", "section"))
        raiz.addLayout(self._nova_nota())
        raiz.addWidget(self._lista_notas(), 1)

        rodape = QHBoxLayout()
        self.aviso = label("", "muted")
        rodape.addWidget(self.aviso, 1)
        fechar = Button("Fechar", "check", "primary")
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)
        rodape.addWidget(fechar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))
        self.carregar_notas()
        self.nova_nota.setFocus()

    # --------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        linha.addWidget(IconBadge("users", "accent", size=44, radius=13))

        textos = QVBoxLayout()
        textos.setSpacing(1)
        textos.addWidget(label(self.contato.nome, "cardTitle"))
        detalhe = []
        if self.contato.documento:
            detalhe.append(
                f"{self.contato.tipo_documento} {self.contato.documento_formatado}"
            )
        if self.contato.idade is not None:
            detalhe.append(f"{self.contato.idade} anos")
        if self.contato.segmento:
            detalhe.append(self.contato.segmento)
        textos.addWidget(label("   ·   ".join(detalhe) or "Sem documento informado", "muted"))
        linha.addLayout(textos, 1)

        linha.addWidget(
            Pill("Ativo", "success") if self.contato.ativo else Pill("Inativo", "muted"),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        return linha

    def _dados(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.sm)
        aniversario = ""
        if self.contato.nascimento:
            aniversario = fmt.data(self.contato.nascimento)

        for titulo, valor in (
            ("Telefone", self.contato.telefone_formatado),
            ("WhatsApp", self.contato.whatsapp_formatado),
            ("E-mail", self.contato.email),
            ("Endereco", self.contato.endereco_completo),
            ("Aniversario", aniversario),
            ("Cadastrado em", fmt.data(self.contato.criado_em)),
            ("Observacoes", self.contato.observacoes),
        ):
            if not (valor or "").strip():
                continue  # ficha nao mostra campo vazio: so ruido
            linha = QHBoxLayout()
            linha.setSpacing(Space.md)
            rotulo = label(titulo, "field")
            rotulo.setFixedWidth(120)
            linha.addWidget(rotulo, 0, Qt.AlignmentFlag.AlignTop)
            texto = label(valor, "body")
            texto.setWordWrap(True)
            texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            linha.addWidget(texto, 1)
            card.body.addLayout(linha)
        return card

    # --------------------------------------------------------------- anotacoes
    def _nova_nota(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.nova_nota = QLineEdit()
        self.nova_nota.setPlaceholderText(
            "O que aconteceu? Ex.: ligou pedindo orcamento de 10 monitores"
        )
        self.nova_nota.returnPressed.connect(self._anotar)
        linha.addWidget(self.nova_nota, 1)

        botao = Button("Anotar", "plus")
        botao.clicked.connect(self._anotar)
        linha.addWidget(botao)
        return linha

    def _lista_notas(self) -> QScrollArea:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.corpo_notas = QWidget()
        self.coluna_notas = QVBoxLayout(self.corpo_notas)
        self.coluna_notas.setContentsMargins(0, 0, Space.sm, 0)
        self.coluna_notas.setSpacing(Space.sm)
        self.scroll.setWidget(self.corpo_notas)
        return self.scroll

    def carregar_notas(self) -> None:
        while self.coluna_notas.count():
            item = self.coluna_notas.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        notas = self.store.notas(self.contato.id)
        if not notas:
            vazio = label(
                "Nenhuma anotacao ainda. Registre o que foi combinado com o cliente "
                "para nao depender da memoria.",
                "dim",
            )
            vazio.setWordWrap(True)
            self.coluna_notas.addWidget(vazio)
        for nota in notas:
            self.coluna_notas.addWidget(self._cartao_nota(nota))
        self.coluna_notas.addStretch(1)

    def _cartao_nota(self, nota) -> Card:
        card = Card(padding=Space.md)
        card.body.setSpacing(Space.xs)

        topo = QHBoxLayout()
        topo.addWidget(label(fmt.data_hora(nota.criado_em), "dim"), 1)
        apagar = Button("", "trash", "ghost")
        apagar.setToolTip("Apagar esta anotacao")
        apagar.setFixedWidth(34)
        apagar.clicked.connect(lambda _=False, i=nota.id: self._apagar_nota(i))
        topo.addWidget(apagar)
        card.body.addLayout(topo)

        texto = label(nota.texto, "body")
        texto.setWordWrap(True)
        card.body.addWidget(texto)
        return card

    def _anotar(self) -> None:
        try:
            self.store.anotar(self.contato.id, self.nova_nota.text())
        except ContatoError as erro:
            self._dizer(str(erro), "danger")
            return
        self.nova_nota.clear()
        self.houve_mudanca = True
        self.carregar_notas()
        self._dizer("Anotacao registrada.", "success")

    def _apagar_nota(self, nota_id: int) -> None:
        self.store.excluir_nota(nota_id)
        self.houve_mudanca = True
        self.carregar_notas()
        self._dizer("Anotacao apagada.")

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)
