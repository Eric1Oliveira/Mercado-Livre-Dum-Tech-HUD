"""O QR Code do Pix, pronto para entrar em qualquer tela que receba dinheiro.

POR QUE ISTO E UM COMPONENTE

A chave Pix e uma so, cadastrada uma vez em Configuracoes > Pagamentos. O
cliente, porem, paga em varios lugares: no balcao, na venda que ficou
pendente, na conta do Financeiro e na retirada da ordem de servico. Enquanto
o desenho do QR morava dentro do dialogo do balcao, cada tela nova nascia sem
Pix - ou pior, com o quadrado em branco.

O QUE ELE SABE FAZER

Recebe a empresa e um valor, e mostra o QR, o copia e cola e para qual chave o
dinheiro vai (o operador confere se alguem trocou a chave). Sem chave
cadastrada, explica onde cadastrar em vez de mostrar um quadrado vazio.

O QUE ELE NAO FAZ

Nao confirma pagamento: o Pix cai na conta do banco, nao aqui. Toda tela que
usa este painel diz isso com todas as letras.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.pix import CobrancaPix, PixError
from ...core.pix import normalizar as normalizar_pix
from ...core.pix import payload as pix_payload
from ...core.pix import tipo_chave as tipo_chave_pix
from ..theme import Space
from .buttons import Button
from .common import Card, label
from .qr import pixmap as qr_pixmap

#: lado do quadrado do QR. Menos que isto e leitor de celular sofrendo.
LADO = 190

SEM_CHAVE = (
    "Cadastre sua chave Pix em Configurações > Pagamentos para o QR Code "
    "aparecer aqui. Você pode receber em Pix mesmo assim."
)


def destino_pix(chave: str) -> str:
    """"CPF final 7735" - o bastante para reconhecer a propria chave."""
    tipo = tipo_chave_pix(chave)
    try:
        normal = normalizar_pix(chave)
    except PixError:
        return "cadastrada"
    if tipo == "e-mail":
        return f"e-mail {normal[:2]}***@{normal.split('@')[-1]}"
    return f"{tipo} final {normal[-4:]}"


class PainelPix(Card):
    """Cartao com o QR Code, o copia e cola e para onde o dinheiro vai."""

    def __init__(self, empresa=None, parent: QWidget | None = None) -> None:
        super().__init__(padding=Space.md, parent=parent)
        self.empresa = empresa
        #: o copia e cola de agora; vazio quando nao da para cobrar por aqui
        self.payload = ""

        linha = QHBoxLayout()
        linha.setSpacing(Space.lg)

        # o QR ignora o tema de proposito: leitor precisa de preto no branco
        self.imagem = label("", "muted")
        self.imagem.setFixedSize(LADO, LADO)
        self.imagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imagem.setStyleSheet("background: #FFFFFF; border-radius: 8px; padding: 0px;")
        linha.addWidget(self.imagem)

        lado = QVBoxLayout()
        lado.setSpacing(Space.xs)
        lado.addWidget(label("Pix copia e cola", "field"))

        self.texto = QLineEdit()
        self.texto.setReadOnly(True)
        # o payload tem ~120 caracteres: sem isto o campo pede a largura toda
        # para ele e estica o dialogo para o dobro do tamanho
        self.texto.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        lado.addWidget(self.texto)

        self.botao_copiar = Button("Copiar código", "file")
        self.botao_copiar.setAutoDefault(False)
        self.botao_copiar.clicked.connect(self.copiar)
        lado.addWidget(self.botao_copiar)

        # a linha mais importante do painel: o sistema NAO ve o pagamento
        self.recado = label("", "dim")
        self.recado.setWordWrap(True)
        lado.addWidget(self.recado)
        lado.addStretch(1)

        linha.addLayout(lado, 1)
        self.body.addLayout(linha)

    # ------------------------------------------------------------------ dados
    def definir_empresa(self, empresa) -> None:
        """A chave mudou em Configuracoes: a tela aberta acompanha."""
        self.empresa = empresa

    def atualizar(self, valor: float) -> None:
        """Refaz o codigo para o valor que esta na tela agora."""
        chave = str(getattr(self.empresa, "pix_chave", "") or "").strip()
        if not chave:
            self._indisponivel(SEM_CHAVE)
            return
        try:
            self.payload = pix_payload(CobrancaPix(
                chave=chave,
                beneficiario=getattr(self.empresa, "nome", "") or "",
                cidade=getattr(self.empresa, "cidade", "") or "",
                valor=float(valor or 0),
            ))
        except PixError as erro:
            self._indisponivel(f"{erro} Corrija em Configurações > Pagamentos.")
            return

        self.imagem.setPixmap(qr_pixmap(self.payload, LADO))
        self.texto.setText(self.payload)
        self.texto.setCursorPosition(0)
        self.texto.setEnabled(True)
        self.botao_copiar.setEnabled(True)
        # o operador ve para onde o dinheiro vai: chave trocada salta aos olhos
        self.recado.setText(
            f"Vai para a chave {destino_pix(chave)}. "
            "Confira o recebimento no seu aplicativo do banco antes de lançar."
        )

    @property
    def tem_qr(self) -> bool:
        return bool(self.payload)

    def copiar(self) -> bool:
        """Manda o copia e cola para a area de transferencia."""
        if not self.payload:
            return False
        QApplication.clipboard().setText(self.payload)
        return True

    def _indisponivel(self, recado: str) -> None:
        """Sem QR, mas o Pix continua sendo forma de pagamento."""
        self.payload = ""
        self.imagem.clear()
        self.texto.clear()
        self.texto.setEnabled(False)
        self.botao_copiar.setEnabled(False)
        self.recado.setText(recado)
