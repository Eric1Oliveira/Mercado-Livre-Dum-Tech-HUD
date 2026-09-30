"""Os dados da empresa - a unica tela que o cliente PRECISA preencher.

Precisa entre aspas: o programa funciona sem ela desde o primeiro dia. Mas e
ela que tira o "COMPROVANTE DE VENDA" anonimo e coloca o nome da loja no papel
que o cliente do cliente leva para casa.

Por isso a tela mostra, ao lado do formulario, **como o documento vai ficar** -
ninguem precisa imprimir para descobrir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.empresa import Empresa, EmpresaError, apagar_logo, guardar_logo
from ...ui.recibo import LARGURA, cabecalho_empresa, centro, linha, rodape_empresa
from ...ui.theme import Space
from ...ui.widgets import form
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import Card, label, repolish, separator, tone_label

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)
ALTURA_LOGO = 64


class Papel(QPlainTextEdit):
    """O papel da previa: sempre as 40 colunas inteiras, caiba onde couber.

    Duas armadilhas moram aqui. A folha de estilo da plataforma define
    `font-size` para todo QPlainTextEdit - e regra de estilo vence `setFont`,
    entao a fonte tem que ser trocada pelo mesmo caminho. E a largura em pixels
    nao da para ser somada na mao, porque o recuo do estilo nao entra na conta
    da moldura. Por isso e a fonte que se ajusta ao espaco, medindo o espaco.
    """

    MENOR, MAIOR = 6.5, 10.5
    #: tamanho de referencia para a regra de tres da largura
    BASE = 10.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previa")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.familia = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        ).family()
        self.tamanho = 0.0
        self._aplicar(self.BASE)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(evento)
        self._ajustar()

    def _ajustar(self) -> None:
        util = self.viewport().width() - 2 * self.document().documentMargin()
        if util <= 0:
            return
        referencia = QFont(self.familia)
        referencia.setPointSizeF(self.BASE)
        largura = QFontMetrics(referencia).horizontalAdvance("0" * LARGURA)
        if largura <= 0:
            return
        cabe = self.BASE * util / largura
        self._aplicar(max(self.MENOR, min(self.MAIOR, cabe)))

    def _aplicar(self, tamanho: float) -> None:
        if abs(tamanho - self.tamanho) < 0.05:
            return
        self.tamanho = tamanho
        self.setStyleSheet(
            f"QPlainTextEdit#previa {{ font-family: '{self.familia}';"
            f" font-size: {tamanho:.1f}pt; }}"
        )


class EmpresaView(QWidget):
    """Formulario dos dados da empresa, com previa do documento ao lado."""

    alterada = Signal()

    def __init__(self, settings, paths=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.paths = paths
        self.empresa = Empresa.carregar(settings)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.lg)

        colunas = QHBoxLayout()
        colunas.setSpacing(Space.lg)
        colunas.addWidget(self._formulario(), 4)
        colunas.addWidget(self._previa(), 3)
        raiz.addLayout(colunas, 1)
        raiz.addLayout(self._acoes())

        self._preencher()

    # ------------------------------------------------------------------ pedacos
    def _formulario(self) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        dentro = QWidget()
        coluna = QVBoxLayout(dentro)
        coluna.setContentsMargins(0, 0, Space.sm, 0)
        coluna.setSpacing(Space.md)

        identidade = Card(padding=Space.lg)
        identidade.body.addWidget(label("Identificacao", "section"))
        identidade.body.addWidget(separator())
        self.nome = form.texto("", "Como a loja e conhecida (aparece no topo)")
        self.nome.textChanged.connect(self._atualizar_previa)
        identidade.body.addWidget(form.campo("Nome fantasia", self.nome))
        self.razao = form.texto("", "Razao social (opcional)")
        self.razao.textChanged.connect(self._atualizar_previa)
        identidade.body.addWidget(form.campo("Razao social", self.razao))
        self.documento = form.texto("", "CNPJ ou CPF")
        self.documento.textChanged.connect(self._atualizar_previa)
        identidade.body.addWidget(form.campo("CNPJ / CPF", self.documento))
        coluna.addWidget(identidade)

        contato = Card(padding=Space.lg)
        contato.body.addWidget(label("Contato", "section"))
        contato.body.addWidget(separator())
        self.telefone = form.texto("", "(00) 0000-0000")
        self.telefone.textChanged.connect(self._atualizar_previa)
        self.whatsapp = form.texto("", "(00) 90000-0000")
        contato.body.addWidget(
            form.linha(form.campo("Telefone", self.telefone),
                       form.campo("WhatsApp", self.whatsapp))
        )
        self.email = form.texto("", "contato@sualoja.com.br")
        self.email.textChanged.connect(self._atualizar_previa)
        contato.body.addWidget(form.campo("E-mail", self.email))
        coluna.addWidget(contato)

        endereco = Card(padding=Space.lg)
        endereco.body.addWidget(label("Endereco", "section"))
        endereco.body.addWidget(separator())
        self.endereco = form.texto("", "Rua, avenida...")
        self.numero = form.texto("", "N.")
        endereco.body.addWidget(
            form.linha(form.campo("Logradouro", self.endereco),
                       form.campo("Numero", self.numero))
        )
        self.bairro = form.texto("", "Bairro")
        self.cep = form.texto("", "00000-000")
        endereco.body.addWidget(
            form.linha(form.campo("Bairro", self.bairro), form.campo("CEP", self.cep))
        )
        self.cidade = form.texto("", "Cidade")
        self.uf = form.escolha([("--", "")] + [(u, u) for u in UFS], "")
        endereco.body.addWidget(
            form.linha(form.campo("Cidade", self.cidade), form.campo("UF", self.uf))
        )
        for campo in (self.endereco, self.numero, self.bairro, self.cep, self.cidade):
            campo.textChanged.connect(self._atualizar_previa)
        self.uf.currentIndexChanged.connect(self._atualizar_previa)
        coluna.addWidget(endereco)

        recebimento = Card(padding=Space.lg)
        recebimento.body.addWidget(label("Recebimento", "section"))
        recebimento.body.addWidget(separator())
        self.pix_aviso = label(
            "A chave Pix e as formas de pagamento ficam em Configuracoes > "
            "Pagamentos, protegidas por um codigo enviado ao e-mail da licenca.",
            "dim",
        )
        self.pix_aviso.setWordWrap(True)
        recebimento.body.addWidget(self.pix_aviso)
        coluna.addWidget(recebimento)

        documento = Card(padding=Space.lg)
        documento.body.addWidget(label("No documento", "section"))
        documento.body.addWidget(separator())

        marca = QHBoxLayout()
        marca.setSpacing(Space.md)
        self.logo = label("", "muted")
        self.logo.setFixedHeight(ALTURA_LOGO)
        self.logo.setMinimumWidth(120)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marca.addWidget(self.logo)
        botoes_logo = QVBoxLayout()
        botoes_logo.setSpacing(Space.xs)
        escolher = Button("Escolher logotipo", "external")
        escolher.clicked.connect(self._escolher_logo)
        botoes_logo.addWidget(escolher)
        self.botao_tirar_logo = Button("Tirar", "trash", "ghost")
        self.botao_tirar_logo.clicked.connect(self._tirar_logo)
        botoes_logo.addWidget(self.botao_tirar_logo)
        marca.addLayout(botoes_logo)
        marca.addStretch(1)
        documento.body.addLayout(marca)
        documento.body.addWidget(
            label("O logotipo sai no PDF da proposta e da ordem de servico.", "dim")
        )

        self.rodape = form.texto("", "Ex.: Obrigado pela preferencia!")
        self.rodape.textChanged.connect(self._atualizar_previa)
        documento.body.addWidget(form.campo("Frase no rodape", self.rodape))
        coluna.addWidget(documento)

        coluna.addStretch(1)
        area.setWidget(dentro)
        return area

    def _previa(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Como o comprovante vai sair", "section"))
        card.body.addWidget(separator())
        self.papel = Papel()
        card.body.addWidget(self.papel, 1)
        return card

    def _acoes(self) -> QHBoxLayout:
        linha_acoes = QHBoxLayout()
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha_acoes.addWidget(self.aviso, 1)
        salvar = Button("Salvar dados da empresa", "check", "primary")
        salvar.setMinimumHeight(38)
        salvar.clicked.connect(self.salvar)
        linha_acoes.addWidget(salvar)
        return linha_acoes

    # ------------------------------------------------------------------- dados
    def _preencher(self) -> None:
        e = self.empresa
        for campo, valor in (
            (self.nome, e.nome), (self.razao, e.razao_social),
            (self.documento, e.documento_formatado),
            (self.telefone, e.telefone_formatado),
            (self.whatsapp, e.whatsapp_formatado if e.whatsapp else ""),
            (self.email, e.email), (self.endereco, e.endereco),
            (self.numero, e.numero), (self.bairro, e.bairro),
            (self.cep, _cep_formatado(e.cep)), (self.cidade, e.cidade),
            (self.rodape, e.rodape),
        ):
            campo.setText(valor)
        indice = self.uf.findData(e.uf)
        self.uf.setCurrentIndex(max(indice, 0))
        self._mostrar_logo()
        self._atualizar_previa()

    def refresh(self) -> None:
        self.empresa = Empresa.carregar(self.settings)
        self._preencher()

    def _montar(self) -> Empresa:
        return Empresa(
            nome=self.nome.text(), razao_social=self.razao.text(),
            documento=self.documento.text(), telefone=self.telefone.text(),
            whatsapp=self.whatsapp.text(), email=self.email.text(),
            endereco=self.endereco.text(), numero=self.numero.text(),
            bairro=self.bairro.text(), cidade=self.cidade.text(),
            uf=self.uf.currentData() or "", cep=self.cep.text(),
            rodape=self.rodape.text(), logo=self.empresa.logo,
        )

    def _atualizar_previa(self) -> None:
        """A previa usa o MESMO motor do comprovante de verdade."""
        empresa = self._montar()
        corpo = [
            centro("COMPROVANTE DE VENDA"),
            linha("="),
            "VEN-2026-0001                 01/09/2026",
            "Cliente: Maria Souza",
            linha(),
            "Produto de exemplo",
            "  2 UN x R$ 25,00              R$ 50,00",
            linha(),
            "TOTAL                          R$ 50,00",
            linha("="),
        ]
        texto = cabecalho_empresa(empresa) + corpo + rodape_empresa(empresa)
        texto.append(centro("Documento sem valor fiscal"))
        self.papel.setPlainText("\n".join(texto))

    def _mostrar_logo(self) -> None:
        caminho = self.empresa.caminho_logo(self.paths)
        if caminho is None:
            self.logo.setPixmap(QPixmap())
            self.logo.setText("sem logotipo")
            self.botao_tirar_logo.setEnabled(False)
            return
        imagem = QPixmap(str(caminho))
        self.logo.setPixmap(
            imagem.scaledToHeight(ALTURA_LOGO, Qt.TransformationMode.SmoothTransformation)
        )
        self.logo.setText("")
        self.botao_tirar_logo.setEnabled(True)

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _escolher_logo(self) -> None:
        arquivo, _ = QFileDialog.getOpenFileName(
            self, "Escolher o logotipo da empresa", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp)",
        )
        if not arquivo:
            return
        try:
            self.empresa.logo = guardar_logo(arquivo, self.paths)
        except EmpresaError as erro:
            self._dizer(str(erro), "danger")
            return
        self.empresa.salvar(self.settings)
        self._mostrar_logo()
        self._dizer("Logotipo guardado.", "success")
        self.alterada.emit()

    def _tirar_logo(self) -> None:
        apagar_logo(self.paths)
        self.empresa.logo = ""
        self.empresa.salvar(self.settings)
        self._mostrar_logo()
        self._dizer("Logotipo removido.")
        self.alterada.emit()

    def salvar(self) -> bool:
        nova = self._montar()
        try:
            nova.salvar(self.settings)
        except EmpresaError as erro:
            self._dizer(str(erro), "danger")
            return False
        self.empresa = nova
        self._dizer(
            "Dados salvos. Eles ja aparecem nos comprovantes e propostas.",
            "success",
        )
        self.alterada.emit()
        return True


def _cep_formatado(valor: str) -> str:
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else digitos


def convite(empresa: Empresa) -> str:
    """A frase do Inicio quando a empresa ainda nao foi preenchida."""
    if empresa.preenchida:
        return ""
    return (
        "Seus comprovantes ainda saem sem o nome da sua empresa. "
        "Preencha em Configuracoes para o cliente saber de quem e o papel."
    )
