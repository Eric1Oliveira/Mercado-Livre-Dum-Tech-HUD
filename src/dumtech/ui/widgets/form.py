"""Formularios: dialogo padrao e campos prontos usados por todos os aplicativos."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Any, Iterable

from PySide6.QtCore import (
    QDate,
    QDateTime,
    QLocale,
    QSortFilterProxyModel,
    QStringListModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import format as fmt
from ..theme import Control, Space, apply_window_theme, palette_for
from .buttons import Button
from .common import label, separator


# ------------------------------------------------------------------- campos ---
def texto(valor: str = "", dica: str = "") -> QLineEdit:
    campo = QLineEdit(valor or "")
    campo.setPlaceholderText(dica)
    return campo


def _simples(texto_bruto: str) -> str:
    """Sem acento e em minusculas: quem digita "sao" acha "Sao" e "Sao Paulo"."""
    decomposto = unicodedata.normalize("NFKD", texto_bruto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


class _FiltroDeSugestoes(QSortFilterProxyModel):
    """Deixa passar quem CONTEM o que foi digitado, ignorando acento."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._termo = ""

    def procurar(self, termo: str) -> None:
        novo = _simples(termo.strip())
        if novo != self._termo:
            self._termo = novo
            self.invalidateFilter()

    def filterAcceptsRow(self, linha: int, pai) -> bool:  # noqa: N802 (Qt)
        if not self._termo:
            return True
        indice = self.sourceModel().index(linha, 0, pai)
        return self._termo in _simples(str(indice.data() or ""))


class Sugestoes(QCompleter):
    """O autocompletar da casa.

    Tres diferencas para o de fabrica, e todas aparecem no balcao:

    * casa no MEIO da palavra - "mouse" acha "Teclado e mouse sem fio";
    * ignora acento - ninguem digita acento com pressa;
    * a lista pode ser trocada depois (`definir`), porque cliente cadastrado
      agora tem de aparecer sem fechar a janela.
    """

    def __init__(self, opcoes: Iterable[str] = (), parent: QWidget | None = None) -> None:
        self.lista = QStringListModel([item for item in opcoes if item])
        self.filtro = _FiltroDeSugestoes()
        self.filtro.setSourceModel(self.lista)
        super().__init__(self.filtro, parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setMaxVisibleItems(10)

    def definir(self, opcoes: Iterable[str]) -> None:
        self.lista.setStringList([item for item in opcoes if item])

    def splitPath(self, caminho: str):  # noqa: N802 (Qt)
        """O Qt pergunta o que filtrar; aqui quem filtra e o proxy.

        Devolver o prefixo vazio faz o Qt mostrar tudo o que passou pelo
        filtro - que e justamente o que casa no meio da palavra.
        """
        self.filtro.procurar(caminho)
        return [""]


def sugestao(valor: str = "", dica: str = "", opcoes: Iterable[str] = ()) -> QLineEdit:
    """Campo de texto com sugestoes (ex.: nome do cliente)."""
    campo = texto(valor, dica)
    campo.setCompleter(Sugestoes(opcoes, campo))
    return campo


def combo_sugestao(valor: str = "", opcoes: Iterable[str] = (),
                   dica: str = "") -> QComboBox:
    """Lista que tambem aceita digitar: escolhe o que existe ou cria na hora.

    Usada onde o valor vem se repetindo mas nao tem cadastro proprio -
    categoria, fornecedor, prateleira, forma de pagamento.
    """
    campo = QComboBox()
    campo.setEditable(True)
    campo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    campo.addItems([""] + [item for item in opcoes if item])
    campo.setCurrentText(valor or "")
    campo.lineEdit().setPlaceholderText(dica)
    campo.setCompleter(Sugestoes(opcoes, campo))
    return campo


def area(valor: str = "", dica: str = "", altura: int = 70) -> QPlainTextEdit:
    campo = QPlainTextEdit(valor or "")
    campo.setPlaceholderText(dica)
    campo.setFixedHeight(altura)
    return campo


def inteiro(valor: int = 0, minimo: int = 0, maximo: int = 9_999_999) -> QSpinBox:
    campo = QSpinBox()
    campo.setRange(minimo, maximo)
    campo.setValue(int(valor or 0))
    campo.setMinimumWidth(110)
    return campo


def quantidade(valor: float = 0.0, casas: int = 0, maximo: float = 9_999_999) -> QDoubleSpinBox:
    """Campo de quantidade. `casas` vem da unidade do produto (0 = so inteiro)."""
    campo = CampoNumero()
    campo.setRange(0, maximo)
    campo.setDecimals(int(casas))
    campo.setValue(float(valor or 0))
    campo.setMinimumWidth(110)
    return campo


class CampoNumero(QDoubleSpinBox):
    """Campo numerico que aceita o que a pessoa digita por cima.

    O campo de fabrica do Qt obriga a apagar o "R$ 0,00" antes de escrever, e
    recusa "1.000,50" porque o ponto nao e separador para ele. Aqui e o
    contrario: ao receber o foco o conteudo ja fica selecionado (digitou,
    trocou) e a leitura entende o jeito brasileiro de escrever numero.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
        self.setGroupSeparatorShown(True)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setKeyboardTracking(False)

    def focusInEvent(self, evento) -> None:  # noqa: N802 (Qt)
        super().focusInEvent(evento)
        # depois do clique: o Qt posiciona o cursor primeiro, a selecao vem apos
        QTimer.singleShot(0, self.selectAll)

    def valueFromText(self, texto: str) -> float:  # noqa: N802 (Qt)
        return fmt.para_numero(texto)

    def validate(self, texto: str, posicao: int):  # noqa: N802 (Qt)
        """Enquanto digita, quase tudo vale - quem decide o valor e a leitura."""
        if not texto.strip() or texto.strip() == self.prefix().strip():
            return QValidator.State.Intermediate, texto, posicao
        return QValidator.State.Acceptable, texto, posicao


def dinheiro(valor: float = 0.0) -> CampoNumero:
    """Campo de dinheiro. Digite 1000 e ele mostra R$ 1.000,00."""
    campo = CampoNumero()
    campo.setRange(0, 99_999_999)
    campo.setDecimals(2)
    campo.setPrefix("R$ ")
    campo.setValue(float(valor or 0))
    campo.setMinimumWidth(140)
    return campo


def escolha(opcoes: Iterable[tuple[str, Any]], atual: Any = None) -> QComboBox:
    campo = QComboBox()
    for rotulo, valor in opcoes:
        campo.addItem(rotulo, valor)
    indice = campo.findData(atual)
    if indice >= 0:
        campo.setCurrentIndex(indice)
    return campo


def data(valor: str | date | None = None) -> QDateEdit:
    campo = QDateEdit()
    campo.setCalendarPopup(True)
    campo.setDisplayFormat("dd/MM/yyyy")
    campo.setDate(_para_qdate(valor))
    campo.setMinimumWidth(140)
    return campo


def data_hora(valor: str | datetime | None = None) -> QDateTimeEdit:
    campo = QDateTimeEdit()
    campo.setCalendarPopup(True)
    campo.setDisplayFormat("dd/MM/yyyy HH:mm")
    momento = QDateTime.currentDateTime()
    if isinstance(valor, datetime):
        momento = QDateTime(valor)
    elif isinstance(valor, str) and valor:
        lido = QDateTime.fromString(valor, Qt.DateFormat.ISODate)
        if lido.isValid():
            momento = lido
    campo.setDateTime(momento)
    campo.setMinimumWidth(180)
    return campo


class CampoData(QLineEdit):
    """Data digitada do jeito de casa: dd/mm/aaaa, com as barras sozinhas.

    Por que nao um QDateEdit? Porque estes campos podem ficar VAZIOS - nem
    todo cliente informa o aniversario - e um QDateEdit sempre tem uma data
    dentro, normalmente a de hoje. Guardar "hoje" como nascimento de quem nao
    quis dizer e inventar dado.

    Para fora, o campo fala ISO (aaaa-mm-dd), que e como o banco guarda e
    ordena. Quem digita nunca ve isso: escreve 07031990 e le 07/03/1990.
    Texto que nao vira data sai como esta, para quem valida reclamar com uma
    mensagem de gente em vez de aceitar em silencio.
    """

    def __init__(self, valor: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("dd/mm/aaaa")
        self.setMaxLength(10)
        self.textEdited.connect(self._pontuar)
        self.definir_iso(valor)

    def _pontuar(self, texto: str) -> None:
        digitos = "".join(c for c in texto if c.isdigit())[:8]
        partes = [digitos[:2], digitos[2:4], digitos[4:8]]
        arrumado = "/".join(parte for parte in partes if parte)
        if arrumado != texto:
            self.setText(arrumado)
            self.setCursorPosition(len(arrumado))

    def definir_iso(self, valor: str | date | None) -> None:
        if isinstance(valor, date):
            self.setText(valor.strftime("%d/%m/%Y"))
            return
        texto_iso = (valor or "").strip()
        if not texto_iso:
            self.setText("")
            return
        lido = QDate.fromString(texto_iso[:10], "yyyy-MM-dd")
        self.setText(lido.toString("dd/MM/yyyy") if lido.isValid() else texto_iso)

    def iso(self) -> str:
        """O que guardar: ISO quando da data, vazio quando vazio."""
        escrito = self.text().strip()
        if not escrito:
            return ""
        lido = QDate.fromString(escrito, "dd/MM/yyyy")
        return lido.toString("yyyy-MM-dd") if lido.isValid() else escrito


def data_opcional(valor: str | date | None = "") -> CampoData:
    """Data que pode ficar em branco, escrita como todo mundo escreve."""
    return CampoData(valor if isinstance(valor, (str, date)) else "")


def _para_qdate(valor: str | date | None) -> QDate:
    if isinstance(valor, date):
        return QDate(valor.year, valor.month, valor.day)
    if isinstance(valor, str) and valor:
        lido = QDate.fromString(valor[:10], "yyyy-MM-dd")
        if lido.isValid():
            return lido
    return QDate.currentDate()


def iso_da_data(campo: QDateEdit) -> str:
    return campo.date().toString("yyyy-MM-dd")


def iso_da_data_hora(campo: QDateTimeEdit) -> str:
    return campo.dateTime().toString("yyyy-MM-ddTHH:mm:00")


def campo(titulo: str, widget: QWidget) -> QWidget:
    """Rotulo pequeno em cima do campo, para telas que nao usam QFormLayout."""
    caixa = QWidget()
    coluna = QVBoxLayout(caixa)
    coluna.setContentsMargins(0, 0, 0, 0)
    coluna.setSpacing(Space.xs)
    coluna.addWidget(label(titulo, "field"))
    coluna.addWidget(widget)
    return caixa


def linha(*widgets: QWidget) -> QWidget:
    """Coloca varios campos lado a lado dentro de uma unica linha do formulario."""
    caixa = QWidget()
    layout = QHBoxLayout(caixa)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget in widgets:
        if isinstance(widget, str):
            layout.addWidget(label(widget, "muted"))
        else:
            layout.addWidget(widget, 1)
    return caixa


# ------------------------------------------------------------------ dialogo ---
class FormDialog(QDialog):
    """Dialogo de cadastro: titulo, formulario e botoes Cancelar/Salvar.

    A subclasse implementa `salvar()`; erros de regra (ValueError e afins) viram
    aviso na tela sem fechar o formulario.
    """

    def __init__(
        self,
        titulo: str,
        subtitulo: str = "",
        parent: QWidget | None = None,
        largura: int = 560,
        rolagem: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(largura)
        # formulario comprido (a ficha da oficina) nao pode passar da tela: com
        # rolagem, o cabecalho e os botoes ficam parados e o meio desliza. Sem
        # uma altura inicial, a area de rolagem nasce apertada e esconde tudo.
        self._rolagem = rolagem
        if rolagem:
            self.resize(largura, 760)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 26, 28, 24)
        raiz.setSpacing(16)

        titulos = QVBoxLayout()
        titulos.setSpacing(3)
        titulos.addWidget(label(titulo, "section"))
        if subtitulo:
            titulos.addWidget(label(subtitulo, "muted"))
        raiz.addLayout(titulos)
        raiz.addWidget(separator())

        miolo = QVBoxLayout()
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(16)
        self.form.setVerticalSpacing(12)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        miolo.addLayout(self.form)

        self.extras = QVBoxLayout()
        self.extras.setSpacing(8)
        miolo.addLayout(self.extras)
        miolo.addStretch(1)

        if rolagem:
            interno = QWidget()
            interno.setLayout(miolo)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(interno)
            raiz.addWidget(area, 1)
        else:
            raiz.addLayout(miolo)

        rodape = QHBoxLayout()
        rodape.setSpacing(Space.sm + 2)
        rodape.addStretch(1)
        cancelar = Button("Cancelar")
        cancelar.setMinimumHeight(38)
        cancelar.clicked.connect(self.reject)
        rodape.addWidget(cancelar)
        self.botao_salvar = Button("Salvar", "check", "primary")
        self.botao_salvar.setMinimumHeight(38)
        self.botao_salvar.setDefault(True)
        self.botao_salvar.clicked.connect(self._tentar_salvar)
        rodape.addWidget(self.botao_salvar)
        raiz.addLayout(rodape)

        apply_window_theme(self, palette_for(parent))

    def add_row(self, rotulo: str, campo) -> None:
        # o rotulo e apoio, nao conteudo: tom baixo, peso medio - o que se le
        # primeiro e o que foi digitado no campo. A altura e a do campo, senao
        # o QFormLayout encosta o rotulo no alto da linha e ele fica torto
        texto = label(rotulo, "field")
        texto.setMinimumHeight(Control.field)
        texto.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.addRow(texto, campo)

    def add_note(self, texto_nota: str) -> None:
        nota = label(texto_nota, "dim")
        nota.setWordWrap(True)
        self.extras.addWidget(nota)

    def salvar(self):
        """Grava os dados.

        Levantar ValueError (ou RegraError) mostra um aviso e mantem o
        formulario aberto. Devolver **False** tambem mantem aberto, mas sem
        caixa nenhuma - para quando a propria tela ja explicou o que falta,
        como o aviso de conflito da Agenda.
        """
        raise NotImplementedError

    def _tentar_salvar(self) -> None:
        try:
            if self.salvar() is False:
                return  # a subclasse pediu para continuar aberta
        except Exception as erro:  # regra de negocio: avisa e mantem aberto
            QMessageBox.warning(self, "Nao foi possivel salvar", str(erro))
            return
        self.accept()
