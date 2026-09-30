"""A janela que abre o WhatsApp com a mensagem escrita.

Ela existe por dois motivos. O primeiro: o texto e editavel antes de sair -
o modelo acerta em quase todo caso, e no caso que sobra quem ajusta e a pessoa,
na hora, sem ir mexer em configuracao. O segundo: nada e enviado por aqui. O
link abre a conversa com o texto pronto e quem aperta enviar e o dono da loja.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.mensagens import MensagemError, link, numero_internacional
from ..theme import Space, apply_window_theme, palette_for
from . import form
from .buttons import Button
from .common import label, repolish, separator


class MensagemDialog(QDialog):
    """Confere o numero, ajusta o texto e abre a conversa."""

    def __init__(
        self,
        texto: str,
        telefone: str = "",
        titulo: str = "Mandar no WhatsApp",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumSize(460, 460)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 24, 26, 22)
        raiz.setSpacing(Space.md)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(2)
        cabecalho.addWidget(label(titulo, "section"))
        cabecalho.addWidget(
            label("Nada e enviado sozinho: o WhatsApp abre com o texto pronto",
                  "muted")
        )
        raiz.addLayout(cabecalho)
        raiz.addWidget(separator())

        self.numero = form.texto(telefone, "(00) 90000-0000")
        self.numero.textChanged.connect(self._conferir)
        raiz.addWidget(form.campo("WhatsApp do cliente", self.numero))

        self.corpo = QPlainTextEdit(texto)
        raiz.addWidget(form.campo("Mensagem", self.corpo), 1)

        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        raiz.addWidget(self.aviso)
        raiz.addLayout(self._botoes())

        apply_window_theme(self, palette_for(parent))
        self._conferir()

    def _botoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        linha.addStretch(1)

        copiar = Button("Copiar texto", "file")
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        self.botao_abrir = Button("Abrir no WhatsApp", "external", "primary")
        self.botao_abrir.setMinimumHeight(38)
        self.botao_abrir.clicked.connect(self._abrir)
        linha.addWidget(self.botao_abrir)

        fechar = Button("Fechar")
        fechar.clicked.connect(self.reject)
        linha.addWidget(fechar)
        return linha

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _conferir(self) -> None:
        """O botao so acende com um numero que o WhatsApp aceita."""
        valido = bool(numero_internacional(self.numero.text()))
        self.botao_abrir.setEnabled(valido)
        if self.numero.text().strip() and not valido:
            self._dizer("Numero incompleto: informe DDD e numero.", "warning")
        elif not self.numero.text().strip():
            self._dizer("Informe o WhatsApp do cliente para abrir a conversa.")
        else:
            self._dizer("")

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.corpo.toPlainText())
        self._dizer("Mensagem copiada.", "success")

    def endereco(self) -> str:
        """Separado do clique para poder ser testado sem abrir navegador."""
        return link(self.numero.text(), self.corpo.toPlainText())

    def _abrir(self) -> None:
        try:
            endereco = self.endereco()
        except MensagemError as erro:
            self._dizer(str(erro), "danger")
            return
        QDesktopServices.openUrl(QUrl(endereco))
        self.accept()


def telefone_do_cliente(contatos, nome: str) -> str:
    """Procura o WhatsApp do cliente na agenda da plataforma.

    Quem nao tiver o DumTech Clientes simplesmente digita o numero na janela -
    por isso nada aqui levanta erro: sem agenda, o campo comeca vazio.
    """
    if contatos is None or not (nome or "").strip():
        return ""
    try:
        contato = contatos.por_nome(nome)
    except Exception:  # noqa: BLE001 - agenda indisponivel nao pode travar o botao
        return ""
    if contato is None:
        return ""
    return contato.whatsapp or contato.telefone


def mandar(
    parent,
    mensageiro,
    chave: str,
    dados: dict,
    telefone: str = "",
    contatos=None,
) -> "MensagemDialog":
    """Monta a mensagem do modelo e abre a janela de envio.

    O caminho e sempre o mesmo em todos os aplicativos: texto do modelo do
    cliente, numero da agenda (quando ha), janela para conferir.
    """
    numero = telefone or telefone_do_cliente(contatos, dados.get("cliente", ""))
    dialogo = MensagemDialog(
        mensageiro.texto(chave, dados), numero,
        f"Mandar no WhatsApp - {dados.get('cliente') or 'cliente'}", parent,
    )
    dialogo.exec()
    return dialogo
