"""Identidade visual da plataforma DumTech: paletas clara e escura.

Regras da casa:

* nenhuma cor fica escrita solta no meio do codigo - tudo vem de uma `Palette`;
* o Hub define o tema da plataforma inteira - inclusive dos aplicativos
  montados nele e dos dialogos abertos de dentro deles;
* trocar de tema nao recria as janelas: a folha de estilo e reaplicada e cada
  widget que desenha cor propria recebe `apply_theme(palette)`.

O visual (setembro/2026) segue uma linguagem so, do Hub ao ultimo dialogo:
fundo quase branco, cartao branco com fio fino, bloco de numero em cinza, um
violeta so como destaque e numero grande em peso alto. O que chama a atencao
e o dado; a moldura fica quieta.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

MODO_ESCURO = "dark"
MODO_CLARO = "light"
MODO_AUTO = "auto"  # usado pelos aplicativos: "seguir o Hub"


@dataclass(frozen=True)
class Palette:
    """Todas as cores usadas pela plataforma em um tema."""

    name: str

    bg: str
    bg_soft: str
    surface: str
    surface_alt: str
    surface_hover: str

    border: str
    border_soft: str
    border_strong: str

    text: str
    text_muted: str
    text_dim: str

    accent: str
    accent_hover: str
    accent_press: str
    accent_soft: str
    on_accent: str

    success: str
    success_soft: str
    on_success: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str

    row_alt: str

    #: azul de informacao - quarta cor dos graficos, nunca alarme
    info: str = "#2F74E0"
    #: lavanda: a fatia "Outros" dos graficos, que nao pode competir com as outras
    accent_muted: str = "#CFC4FC"
    #: as duas pontas do degrade da faixa de abertura do Inicio
    hero_a: str = "#6344EE"
    hero_b: str = "#9D88FB"

    @property
    def is_dark(self) -> bool:
        return self.name == MODO_ESCURO

    def resolve(self, color: str | None) -> str:
        """Aceita tanto um nome de cor da paleta ("accent") quanto um #hex."""
        if not color:
            return self.text
        if color.startswith("#"):
            return color
        return getattr(self, color, self.text)


DARK = Palette(
    name=MODO_ESCURO,
    bg="#0D0D12",
    bg_soft="#13131A",
    surface="#17171F",
    surface_alt="#1E1E28",
    surface_hover="#272732",
    border="#2B2B37",
    border_soft="#22222C",
    border_strong="#3A3A48",
    text="#F1F1F6",
    text_muted="#A3A3B5",
    text_dim="#707085",
    accent="#7C62F6",
    accent_hover="#8D77F8",
    accent_press="#6A4FEA",
    accent_soft="#262046",
    on_accent="#FFFFFF",
    success="#3DD68C",
    success_soft="#11291E",
    on_success="#06231A",
    warning="#F5A524",
    warning_soft="#33250C",
    danger="#F26B6B",
    danger_soft="#361A1B",
    row_alt="#15151C",
    info="#5B9BFF",
    accent_muted="#4B4180",
    hero_a="#5234DC",
    hero_b="#8670F4",
)

LIGHT = Palette(
    name=MODO_CLARO,
    bg="#F6F6F9",
    bg_soft="#FFFFFF",
    surface="#FFFFFF",
    surface_alt="#F0F0F4",
    surface_hover="#E8E8EE",
    border="#E3E3EA",
    border_soft="#ECECF1",
    border_strong="#D2D2DC",
    text="#15151C",
    text_muted="#666677",
    text_dim="#8E8E9F",
    accent="#7353F6",
    accent_hover="#8266F8",
    accent_press="#6041E8",
    accent_soft="#EFEBFE",
    on_accent="#FFFFFF",
    success="#16834A",
    success_soft="#E3F5EA",
    on_success="#FFFFFF",
    warning="#B86E00",
    warning_soft="#FDF1DC",
    danger="#D63B3B",
    danger_soft="#FDECEC",
    row_alt="#FAFAFC",
)

PALETTES: dict[str, Palette] = {DARK.name: DARK, LIGHT.name: LIGHT}


def palette_by_name(name: str | None) -> Palette:
    return PALETTES.get(name or MODO_ESCURO, DARK)


#: Quieto por padrao, alto so quando ha problema.
#:
#: Cada numero da plataforma vem com um tom (o modulo diz se aquilo e receita,
#: despesa, atraso). Pintar TODOS eles fazia o arco-iris em que nada se
#: destaca: verde em "voce tem dinheiro" e azul em "vendeu hoje" sao fatos
#: normais, nao avisos. So o que precisa de acao fica colorido - e quando um
#: numero normal vira problema (saldo negativo, prazo estourado), o proprio
#: modulo troca o tom para `danger` e ele acende sozinho.
TONS_DE_ALARME = ("danger", "warning")


def tom_visivel(tom: str) -> str:
    """O tom que o numero realmente usa na tela."""
    return tom if tom in TONS_DE_ALARME else "text"


class Space:
    """Escala de espacamento (base 4). Use estes nomes, nao numeros soltos."""

    xs = 4
    sm = 8
    md = 12
    lg = 16
    xl = 24
    xxl = 32
    xxxl = 48


class Radius:
    sm = 8
    md = 10
    lg = 14
    xl = 18
    #: Qt nao arredonda "ate a metade da altura" sozinho, entao a etiqueta
    #: arredondada tem um valor fixo, casado com a altura real da Pill.
    pill = 11


class Metrics:
    """Apelidos historicos, mantidos para nao quebrar chamadas existentes."""

    radius = Radius.md
    radius_lg = Radius.lg
    gap = Space.lg
    padding = Space.xl - 2  # 22


class Control:
    """Alturas dos controles. Confortavel para o dedo, sem virar folgado."""

    compact = 32
    default = 36
    primary = 40
    field = 36


# ------------------------------------------------------------- tipografia ---
#
# Qt NAO suporta `letter-spacing` em folha de estilo: tracking so existe via
# QFont. Por isso a tipografia da plataforma mora aqui, em Python, e a folha de
# estilo cuida apenas de cor. Quem cria um rotulo usa `ui.widgets.common.label`,
# que aplica o papel tipografico pelo nome.


@dataclass(frozen=True)
class TypeSpec:
    size: float           # em pontos
    weight: int = 400     # 400 / 500 / 600 / 700 / 800
    tracking: float = 0.0  # em pixels, absoluto
    upper: bool = False
    mono: bool = False


# Numero e titulo em peso alto, texto de apoio em peso medio. Rotulo de campo e
# de secao em frase normal, nao em CAIXA ALTA: quem organiza a tela e o peso e
# o tamanho, nao o grito.
TYPE: dict[str, TypeSpec] = {
    # titulos
    "hero": TypeSpec(22.0, 800, -0.6),
    "display": TypeSpec(20.0, 800, -0.5),
    "title": TypeSpec(16.0, 800, -0.35),
    "section": TypeSpec(11.5, 700, -0.2),
    "cardTitle": TypeSpec(11.0, 700, -0.15),
    # corpo
    "body": TypeSpec(9.5, 500),
    "subtitle": TypeSpec(10.0, 500),
    "muted": TypeSpec(9.5, 500),
    "strong": TypeSpec(9.5, 700),
    # apoio
    "caption": TypeSpec(8.5, 500),
    "dim": TypeSpec(8.5, 500),
    "overline": TypeSpec(8.5, 600, 0.1),
    "field": TypeSpec(8.8, 600),
    # navegacao
    "tab": TypeSpec(9.5, 600),
    "kbd": TypeSpec(7.5, 700, 0.3),
    # numeros - o numero e o assunto da linha, entao ele domina
    "metric": TypeSpec(21.0, 800, -0.6),
    #: numero de apoio, para a faixa de indicadores que nao e o foco da tela
    "metricSoft": TypeSpec(17.0, 800, -0.4),
    "mono": TypeSpec(9.5, 500, mono=True),
    # marca
    "brand": TypeSpec(12.5, 800, -0.3),
    "brandSub": TypeSpec(7.5, 700, 1.6, upper=True),
}

BASE_SIZE = 9.5
#: texto das celulas de tabela e dos itens de lista
TAMANHO_LISTA = 9.0

#: A fonte vem junto com o programa (pasta `fonts/`, licenca OFL): assim a tela
#: e a mesma em qualquer Windows, e nao depende do que estiver instalado.
_TEXT_FAMILIES = ("Plus Jakarta Sans", "Segoe UI Variable Text", "Segoe UI", "Noto Sans")
_MONO_FAMILIES = ("Cascadia Mono", "Consolas", "Segoe UI Mono", "Courier New")
_PASTA_FONTES = Path(__file__).resolve().parent / "fonts"

_fontes_carregadas = False


def carregar_fontes() -> None:
    """Registra as fontes que acompanham o programa (uma vez so)."""
    global _fontes_carregadas
    if _fontes_carregadas or QGuiApplication.instance() is None:
        return
    _fontes_carregadas = True
    for arquivo in sorted(_PASTA_FONTES.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(arquivo))


def _first_available(candidates: tuple[str, ...]) -> str:
    carregar_fontes()
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return candidates[-1]


_text_family: str | None = None
_mono_family: str | None = None


def text_family() -> str:
    global _text_family
    if _text_family is None:
        _text_family = _first_available(_TEXT_FAMILIES)
    return _text_family


def mono_family() -> str:
    global _mono_family
    if _mono_family is None:
        _mono_family = _first_available(_MONO_FAMILIES)
    return _mono_family


@lru_cache(maxsize=1)
def _tag_tnum():
    """A etiqueta OpenType dos numeros de largura fixa, do jeito que o Qt pede.

    Calculada UMA vez. Rodava a cada rotulo criado, e a tentativa que falha
    passa pelo caminho de erro do PySide, que monta a mensagem com `eval`:
    ~0,5 ms por rotulo, ~75 ms so para abrir um aplicativo.

    `setFeature("tnum", 1)` - com texto - e recusado pelo PySide com TypeError.
    O PySide 6.8 tambem nao sabe montar a etiqueta a partir de texto (`Tag` so
    tem o construtor vazio), entao aqui ela sai None e os numeros seguem
    proporcionais; numa versao que tenha `Tag.fromString`, liga sozinho.
    """
    # So o caminho que existe. Tentar `QFont.Tag("tnum")` no PySide 6.8 sempre
    # falha - e a primeira falha carrega o maquinario de mensagens de erro do
    # PySide inteiro: ~80 ms na abertura do programa, para nada.
    fabrica = getattr(QFont.Tag, "fromString", None)
    if fabrica is None:
        return None
    try:
        return fabrica("tnum")
    except (TypeError, ValueError):
        return None


def _tabular(font: QFont) -> QFont:
    """Numeros de largura fixa: colunas de dinheiro param de dancar."""
    tag = _tag_tnum()
    if tag is not None:
        try:
            font.setFeature(tag, 1)
        except (AttributeError, TypeError):
            pass  # Qt antigo: segue com os numeros proporcionais
    return font


def base_font() -> QFont:
    """Fonte padrao da plataforma."""
    font = QFont(text_family())
    font.setPointSizeF(BASE_SIZE)
    font.setWeight(QFont.Weight(500))
    return _tabular(font)


#: fonte pronta por papel: montar QFont a cada rotulo e pintura custava caro
_fontes_prontas: dict[str, QFont] = {}


def font_for(role: str) -> QFont:
    """Fonte de um papel tipografico ("title", "overline", "metric"...).

    Devolve uma copia: quem recebe pode mexer (tamanho, peso) sem estragar a
    fonte guardada.
    """
    pronta = _fontes_prontas.get(role)
    if pronta is None:
        spec = TYPE.get(role)
        if spec is None:
            return base_font()
        pronta = QFont(mono_family() if spec.mono else text_family())
        pronta.setPointSizeF(spec.size)
        pronta.setWeight(QFont.Weight(spec.weight))
        if spec.tracking:
            pronta.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spec.tracking)
        if spec.upper:
            pronta.setCapitalization(QFont.Capitalization.AllUppercase)
        _tabular(pronta)
        _fontes_prontas[role] = pronta
    return QFont(pronta)


def apply_type(widget: QWidget, role: str) -> None:
    """Aplica um papel tipografico a um widget."""
    if role in TYPE:
        widget.setFont(font_for(role))


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


def rgba(hex_color: str, alpha: float) -> str:
    """Cor com transparencia no formato que a folha de estilo entende."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.3f})"


def mix(base: str, over: str, amount: float) -> str:
    """Mistura duas cores solidas (para tingir superficies com a cor do app)."""
    a, b = QColor(base), QColor(over)
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount),
    ).name()


# ------------------------------------------------------------- folha de estilo ---
def build_stylesheet(p: Palette) -> str:
    """Monta a folha de estilo (QSS) inteira para uma paleta."""
    pill = (f"border-radius: {Radius.pill}px; padding: 3px 10px; "
            f"font-size: 8.5pt; font-weight: 600;")
    return f"""* {{
    outline: 0;
}}

QWidget {{
    color: {p.text};
}}

QMainWindow, QScrollArea, QStackedWidget {{
    background-color: {p.bg};
}}
QDialog {{
    background-color: {p.surface};
}}
QDialog QStackedWidget {{
    background-color: transparent;
}}
QScrollArea#MioloDialogo {{
    background-color: transparent;
}}

QToolTip {{
    background-color: {p.text};
    color: {p.surface};
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 600;
}}

/* ---------------------------------------------------------------- textos --- */
/* Tamanho, peso e tracking vem do QFont (ver TYPE em theme.py). Aqui, so cor. */
QLabel[role="hero"] {{ color: {p.text}; }}
QLabel[role="display"] {{ color: {p.text}; }}
QLabel[role="title"] {{ color: {p.text}; }}
QLabel[role="subtitle"] {{ color: {p.text_muted}; }}
QLabel[role="section"] {{ color: {p.text}; }}
QLabel[role="body"] {{ color: {p.text}; }}
QLabel[role="muted"] {{ color: {p.text_muted}; }}
QLabel[role="caption"] {{ color: {p.text_muted}; }}
QLabel[role="dim"] {{ color: {p.text_dim}; }}
QLabel[role="overline"] {{ color: {p.text_muted}; }}
QLabel[role="metric"] {{ color: {p.text}; }}
QLabel[role="metricSoft"] {{ color: {p.text}; }}
QLabel[role="mono"] {{ color: {p.text}; }}
QLabel[role="tab"] {{ color: {p.text_muted}; }}

/* ----------------------------------------------------------------- caixas --- */
/* Duas superficies, e so duas: o cartao branco com fio (listas, graficos,
   formularios) e o bloco cinza sem fio (numeros). */
QFrame[role="card"] {{
    background-color: {p.surface};
    border: 1px solid {p.border_soft};
    border-radius: {Radius.lg}px;
}}
QFrame[role="tile"] {{
    background-color: {p.surface_alt};
    border: 1px solid {p.surface_alt};
    border-radius: {Radius.lg}px;
}}
QFrame[role="tile"][clicavel="true"]:hover {{
    border: 1px solid {p.border};
}}
QFrame[role="panel"] {{
    background-color: {p.surface};
    border: 1px solid {p.border_soft};
    border-radius: {Radius.md}px;
}}
QFrame[role="plain"] {{
    background-color: transparent;
    border: none;
}}
QFrame[role="separator"] {{
    /* a espessura vem do Python (`common.separator`), que sabe se o fio e
       horizontal ou vertical; um `max-height` aqui achatava o vertical */
    background-color: {p.border_soft};
    border: none;
}}
QFrame[role="dash"] {{
    background-color: transparent;
    border: none;
    border-top: 1px dashed {p.border};
}}
/* dentro de um cartao, todo fio e tracejado - o de lista e o de secao. Um
   fio cheio no meio do cartao parecia tabela, e cada modulo desenhava o seu
   de um jeito; assim a plataforma inteira fala a mesma lingua. */
QFrame[role="card"] QFrame[role="separator"] {{
    background-color: transparent;
    border: none;
    border-top: 1px dashed {p.border};
}}

/* ------------------------------------------------------ barra do Hub --- */
#TopBar {{
    background-color: {p.surface};
    border: none;
    border-bottom: 1px solid {p.border_soft};
}}
#ViewTrack {{
    background-color: {p.surface_alt};
    border: none;
    border-radius: {Radius.md + 1}px;
}}

/* ---------------------------------------------------------------- botoes --- */
QPushButton {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: {Radius.md}px;
    padding: 7px 15px;
    font-size: {BASE_SIZE}pt;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {p.surface_alt};
    border-color: {p.border_strong};
}}
QPushButton:pressed {{
    background-color: {p.surface_hover};
}}
/* foco visivel: `* {{ outline: 0 }}` apaga o foco do Qt, entao cada controle
   redesenha o seu. Sem isso, navegar pelo teclado e invisivel. */
QPushButton:focus {{
    border-color: {p.accent};
}}
QPushButton:disabled {{
    color: {p.text_dim};
    background-color: {p.surface};
    border-color: {p.border_soft};
}}

QPushButton[variant="primary"] {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    color: {p.on_accent};
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background-color: {p.accent_press};
    border-color: {p.accent_press};
}}
QPushButton[variant="primary"]:focus {{
    border-color: {p.text};
}}
QPushButton[variant="primary"]:disabled {{
    background-color: {p.accent_soft};
    border-color: {p.accent_soft};
    color: {p.text_dim};
}}

QPushButton[variant="success"] {{
    background-color: {p.success};
    border: 1px solid {p.success};
    color: {p.on_success};
    font-weight: 700;
}}
QPushButton[variant="success"]:hover {{
    background-color: {p.success};
    border-color: {p.text};
}}

QPushButton[variant="danger"] {{
    background-color: {p.danger_soft};
    border: 1px solid {p.danger_soft};
    color: {p.danger};
}}
QPushButton[variant="danger"]:hover {{
    border-color: {p.danger};
}}
QPushButton[variant="danger"]:focus {{
    border-color: {p.danger};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {p.text_muted};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {p.surface_alt};
    color: {p.text};
}}
QPushButton[variant="ghost"]:focus {{
    border-color: {p.accent};
    color: {p.text};
}}

/* botao so de icone (tema, fechar): quadrado, com fio, como na barra do Hub */
QPushButton[variant="icon"] {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    padding: 0px;
}}
QPushButton[variant="icon"]:hover {{
    background-color: {p.surface_alt};
    border-color: {p.border_strong};
}}

/* sobre o degrade violeta do Inicio: vidro claro e link branco */
QPushButton[variant="hero"] {{
    background-color: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.30);
    color: #FFFFFF;
    font-weight: 700;
}}
QPushButton[variant="hero"]:hover {{
    background-color: rgba(255, 255, 255, 0.26);
    border-color: rgba(255, 255, 255, 0.45);
}}
QPushButton[variant="heroLink"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: rgba(255, 255, 255, 0.88);
    font-weight: 600;
}}
QPushButton[variant="heroLink"]:hover {{
    color: #FFFFFF;
    background-color: rgba(255, 255, 255, 0.10);
}}

/* desabilitado vale para TODAS as variantes: um botao colorido que nao faz
   nada e um convite a clicar em falso */
QPushButton[variant="success"]:disabled,
QPushButton[variant="danger"]:disabled,
QPushButton[variant="ghost"]:disabled,
QPushButton[variant="icon"]:disabled {{
    background-color: {p.surface};
    border: 1px solid {p.border_soft};
    color: {p.text_dim};
}}
QPushButton::menu-indicator {{
    image: none;
    width: 0px;
}}

/* ------------------------------------------------------------- formulario --- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QDateTimeEdit, QTimeEdit {{
    background-color: {p.bg_soft};
    border: 1px solid {p.border};
    border-radius: {Radius.md}px;
    padding: 6px 11px;
    min-height: 22px;
    font-size: {BASE_SIZE}pt;
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
}}
QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit {{
    padding-right: 28px;
}}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QDateTimeEdit:hover {{
    border-color: {p.border_strong};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus {{
    border-color: {p.accent};
    background-color: {p.surface};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {p.text_dim};
    background-color: {p.surface_alt};
    border-color: {p.border_soft};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_muted};
    width: 0px;
    height: 0px;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {Radius.md}px;
    padding: 4px;
    selection-background-color: {p.surface_alt};
    selection-color: {p.text};
    outline: 0;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    background-color: transparent;
    border: none;
    border-radius: 5px;
    width: 20px;
    height: 15px;
    margin: 3px 4px 0px 0px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    background-color: transparent;
    border: none;
    border-radius: 5px;
    width: 20px;
    height: 15px;
    margin: 0px 4px 3px 0px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover,
QDateEdit::up-button:hover, QDateTimeEdit::up-button:hover,
QDateEdit::down-button:hover, QDateTimeEdit::down-button:hover {{
    background-color: {p.surface_alt};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QDateTimeEdit::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {p.text_muted};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_muted};
}}

QCheckBox, QRadioButton {{
    spacing: 9px;
    color: {p.text_muted};
}}
QCheckBox:hover, QRadioButton:hover {{
    color: {p.text};
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 6px;
    border: 1px solid {p.border_strong};
    background-color: {p.bg_soft};
}}
QCheckBox::indicator:hover {{
    border-color: {p.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {p.border_strong};
    background-color: {p.bg_soft};
}}
QRadioButton::indicator:checked {{
    border: 5px solid {p.accent};
    background-color: {p.surface};
}}

QProgressBar {{
    background-color: {p.surface_alt};
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    color: transparent;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 4px;
}}

QListWidget {{
    background-color: {p.surface};
    border: 1px solid {p.border_soft};
    border-radius: {Radius.md}px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 7px 10px;
    border-radius: 8px;
    color: {p.text};
}}
QListWidget::item:hover {{
    background-color: {p.surface_alt};
}}
QListWidget::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}

/* ------------------------------------------------------------------ tabela --- */
QTableView, QTableWidget {{
    background-color: {p.surface};
    alternate-background-color: {p.row_alt};
    border: 1px solid {p.border_soft};
    border-radius: {Radius.lg}px;
    gridline-color: transparent;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    padding: 2px 4px 4px 4px;
}}
QTableView::item, QTableWidget::item {{
    padding: 6px 12px;
    border: none;
    border-bottom: 1px solid {p.border_soft};
}}
QTableView:focus, QTableWidget:focus {{
    border-color: {p.border};
}}
QTableView::item:selected, QTableWidget::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}
/* cabecalho transparente: quem pinta o fundo arredondado e a propria tabela;
   um cabecalho com cor propria deixava os cantos quadrados vazando do raio */
QHeaderView {{
    background-color: transparent;
    border: none;
}}
QHeaderView::section {{
    background-color: transparent;
    color: {p.text_muted};
    padding: 11px 12px 10px 12px;
    border: none;
    border-bottom: 1px solid {p.border_soft};
    font-weight: 600;
    font-size: 8.5pt;
}}
QTableCornerButton::section {{
    background-color: transparent;
    border: none;
}}
/* tabela que ja mora num cartao nao desenha a propria moldura: seriam dois
   fios e dois raios, um dentro do outro */
QFrame[role="card"] QTableView, QFrame[role="card"] QTableWidget {{
    border: none;
    border-radius: 0px;
    padding: 0px;
    background-color: transparent;
}}

/* -------------------------------------------------------------- calendario --- */
/* O calendario e uma QTableView por dentro. Sem estas regras ele herda o
   recuo e a borda das listas do programa, e a grade dos dias sai deformada:
   as colunas nao fecham a semana e o cabecalho dos dias some. */
QCalendarWidget QWidget {{
    alternate-background-color: {p.surface};
}}
QCalendarWidget QAbstractItemView {{
    background-color: {p.surface};
    border: none;
    border-radius: 0px;
    padding: 0px;
    outline: none;
    color: {p.text};
    gridline-color: transparent;
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
    font-size: {BASE_SIZE}pt;
}}
QCalendarWidget QAbstractItemView::item {{
    padding: 0;
    border: none;
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {p.text_dim};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {p.surface};
    border-bottom: 1px solid {p.border_soft};
    min-height: 38px;
}}
QCalendarWidget QToolButton {{
    background-color: transparent;
    color: {p.text};
    border: none;
    border-radius: {Radius.sm}px;
    padding: 5px 10px;
    font-weight: 700;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {p.surface_alt};
}}
QCalendarWidget QToolButton::menu-indicator {{
    image: none;
    width: 0;
}}
QCalendarWidget QSpinBox {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: {Radius.sm}px;
    margin: 3px;
}}

/* ------------------------------------------------------------------ barras --- */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 3px 2px 3px 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 3px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.text_dim};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 3px 2px 3px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 3px;
    min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p.text_dim};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QStatusBar {{
    background-color: {p.surface};
    color: {p.text_dim};
    border-top: 1px solid {p.border_soft};
}}
QStatusBar::item {{
    border: none;
}}

QMenu {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 26px 8px 12px;
    border-radius: 8px;
    color: {p.text};
}}
QMenu::item:selected {{
    background-color: {p.surface_alt};
}}
QMenu::item:disabled {{
    color: {p.text_dim};
}}
QMenu::icon {{
    padding-left: 10px;
}}
QMenu::separator {{
    height: 1px;
    background: {p.border_soft};
    margin: 5px 6px;
}}
QMenu::indicator {{
    width: 0px;
}}

QMessageBox {{
    background-color: {p.surface};
}}
QMessageBox QLabel {{
    color: {p.text};
}}

/* --------------------------------------------------------- textos extras --- */
QLabel[role="strong"] {{ color: {p.text}; }}
QLabel[role="brand"] {{ color: {p.text}; }}
QLabel[role="brandSub"] {{ color: {p.text_muted}; }}
QLabel[role="cardTitle"] {{ color: {p.text}; }}
QLabel[role="field"] {{ color: {p.text_muted}; }}
QLabel[role="kbd"] {{
    color: {p.text_muted};
    background-color: {p.surface_alt};
    border: 1px solid {p.border_soft};
    border-radius: 5px;
    padding: 1px 5px;
}}

/* ------------------------------------------------------------- etiquetas --- */
QLabel[pill="accent"] {{
    background-color: {p.accent_soft};
    color: {p.accent};
    {pill}
}}
QLabel[pill="success"] {{
    background-color: {p.success_soft};
    color: {p.success};
    {pill}
}}
QLabel[pill="warning"] {{
    background-color: {p.warning_soft};
    color: {p.warning};
    {pill}
}}
QLabel[pill="danger"] {{
    background-color: {p.danger_soft};
    color: {p.danger};
    {pill}
}}
QLabel[pill="muted"] {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    {pill}
}}

/* ------------------------------------------------------ valores coloridos --- */
QLabel[tone="text"] {{ color: {p.text}; }}
QLabel[tone="muted"] {{ color: {p.text_muted}; }}
QLabel[tone="accent"] {{ color: {p.accent}; }}
QLabel[tone="success"] {{ color: {p.success}; }}
QLabel[tone="warning"] {{ color: {p.warning}; }}
QLabel[tone="danger"] {{ color: {p.danger}; }}

/* texto sobre o degrade violeta: branco, e branco suave para o apoio */
QLabel[onhero="1"] {{ color: #FFFFFF; }}
QLabel[onhero="soft"] {{ color: rgba(255, 255, 255, 0.80); }}

/* ----------------------------------------------------------- menu lateral --- */
NavButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {Radius.md}px;
    color: {p.text_muted};
    text-align: left;
    padding: 8px 12px;
    font-size: {BASE_SIZE}pt;
    font-weight: 600;
}}
NavButton:hover {{
    background-color: {p.surface_alt};
    color: {p.text};
}}
NavButton:checked {{
    background-color: {p.surface};
    border-color: {p.border_soft};
    color: {p.text};
    font-weight: 700;
}}
NavButton:focus {{
    border-color: {p.accent};
    color: {p.text};
}}

/* ------------------------------------------------ seletor de telas (apps) --- */
/* O segmento escolhido nao pinta fundo: a pilula branca e o `Indicador` do
   trilho, que desliza de uma tela para a outra. Mora aqui, e nao numa folha
   em cada aba: folha propria por widget era um `setStyleSheet` a mais por aba
   a cada troca de tema. As regras repetem o fundo transparente nos estados
   porque `QPushButton:hover` (mais especifico) pintaria o fundo do botao. */
ViewTab, ViewTab:hover, ViewTab:pressed, ViewTab:checked {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {Radius.sm}px;
    padding: 6px 15px;
    margin: 0px;
    color: {p.text_muted};
    font-weight: 600;
}}
ViewTab:hover, ViewTab:checked {{
    color: {p.text};
}}
ViewTab:focus {{
    border: 1px solid {p.accent};
}}
/* tela nova: a aba abre espaco a direita para a etiqueta "Novo", que ela
   mesma pinta (`ViewTab.FOLGA_NOVO`) */
ViewTab[novo="true"], ViewTab[novo="true"]:hover,
ViewTab[novo="true"]:pressed, ViewTab[novo="true"]:checked {{
    padding-right: 52px;
}}
"""


# ---------------------------------------------------------------- aplicacao ---
def _arrow_rules(p: Palette) -> str:
    """Setas de combo/spin e marca do checkbox, desenhadas com os icones."""
    from . import icons

    baixo = icons.asset("caret-down", p.text_muted, 14)
    cima = icons.asset("caret-up", p.text_muted, 14)
    marca = icons.asset("check", p.on_accent, 14, 2.6)
    # o calendario vem com setas verdes de fabrica, que nao sao deste programa
    voltar = icons.asset("back", p.text_muted, 16, 2.4)
    avancar = icons.asset("forward", p.text_muted, 16, 2.4)
    return f"""
QComboBox::down-arrow {{
    image: url("{baixo}");
    width: 12px;
    height: 12px;
    border: none;
    margin-right: 9px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QDateTimeEdit::up-arrow {{
    image: url("{cima}");
    width: 11px;
    height: 11px;
    border: none;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: url("{baixo}");
    width: 11px;
    height: 11px;
    border: none;
}}
QCheckBox::indicator:checked {{
    image: url("{marca}");
}}
QCalendarWidget QToolButton#qt_calendar_prevmonth {{
    qproperty-icon: url("{voltar}");
    icon-size: 14px 14px;
}}
QCalendarWidget QToolButton#qt_calendar_nextmonth {{
    qproperty-icon: url("{avancar}");
    icon-size: 14px 14px;
}}
"""


def stylesheet_for(p: Palette) -> str:
    return build_stylesheet(p) + _arrow_rules(p)


def qt_palette(p: Palette) -> QPalette:
    """Paleta base do Qt (cobre o que a folha de estilo nao alcanca)."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(p.bg))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(p.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(p.bg_soft))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(p.row_alt))
    palette.setColor(QPalette.ColorRole.Text, QColor(p.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(p.surface))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(p.text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(p.text))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(p.surface))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(p.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(p.on_accent))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(p.text_dim))
    for papel in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                  QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, papel, QColor(p.text_dim))
    return palette


_atual: Palette = DARK


def current_palette() -> Palette:
    """Paleta da plataforma (usada por widgets criados fora de uma janela)."""
    return _atual


def set_current_palette(p: Palette) -> None:
    global _atual
    _atual = p


def palette_for(widget: QWidget | None) -> Palette:
    """Descobre o tema da janela onde o widget vive (dialogos herdam do pai).

    So janela carrega tema: `apply_window_theme` marca janelas. Um carimbo num
    widget que hoje esta dentro de outra janela e sobra de quando ele era
    janela - se fosse aceito, o dialogo abriria com um tema congelado.
    """
    while widget is not None:
        marcada = getattr(widget, "_dt_palette", None)
        if marcada is not None and widget.isWindow():
            return marcada
        widget = widget.parent()
    return current_palette()


def refresh_theme(root: QWidget, p: Palette) -> None:
    """Avisa todo widget que desenha cor propria que o tema mudou."""
    for widget in [root, *root.findChildren(QWidget)]:
        aplicar = getattr(widget, "apply_theme", None)
        if callable(aplicar):
            try:
                aplicar(p)
            except RuntimeError:
                pass  # widget ja destruido pelo Qt


def apply_window_theme(window: QWidget, p: Palette) -> None:
    """Aplica um tema a uma janela inteira (e so a ela).

    Toda janela da plataforma passa por aqui - o Hub e cada dialogo - e por
    isso e aqui que ela ganha a barra de titulo na cor do tema e a entrada
    suave ao abrir.
    """
    from . import chrome, motion

    window._dt_palette = p
    window.setPalette(qt_palette(p))
    window.setStyleSheet(stylesheet_for(p))
    refresh_theme(window, p)
    motion.acompanhar(window)
    chrome.pintar(window, p)


#: Classes para as quais o Windows guarda uma fonte propria (Segoe UI).
#: `app.setFont(fonte)` sozinho nao chega nelas: as celulas de toda tabela, os
#: menus, as dicas e as caixas de mensagem continuavam no Segoe - invisivel
#: enquanto a fonte da plataforma era o proprio Segoe, gritante agora.
_FONTE_POR_CLASSE = (
    "QAbstractItemView", "QHeaderView", "QMenu", "QMenuBar", "QTipLabel",
    "QStatusBar", "QMessageBox", "QMessageBoxLabel",
)


def _fonte_nas_classes(app: QApplication) -> None:
    """Repoe a fonte da plataforma nas classes que o Windows guarda a parte.

    Precisa rodar DEPOIS de todo `app.setStyleSheet`: trocar a folha de estilo
    da aplicacao faz o Qt reler as fontes do sistema para essas classes. Hoje
    a folha da aplicacao e posta uma vez so (`ThemeManager`).
    """
    fonte = base_font()
    # lista e tabela meio ponto abaixo do texto corrido: as colunas de largura
    # fixa dos modulos foram medidas no Segoe, que e mais estreito
    lista = QFont(fonte)
    lista.setPointSizeF(TAMANHO_LISTA)
    for classe in _FONTE_POR_CLASSE:
        app.setFont(lista if classe == "QAbstractItemView" else fonte, classe)


def aplicar_fonte(app: QApplication) -> None:
    """A fonte da plataforma em todo lugar, inclusive nas classes do Windows."""
    app.setFont(base_font())  # este limpa as fontes por classe; a de baixo repoe
    _fonte_nas_classes(app)


#: A unica folha da APLICACAO - e ela nunca muda depois de posta.
#:
#: Trocar a folha da aplicacao obriga o Qt a reestilizar todo widget do
#: programa, visivel ou nao: com sete aplicativos abertos eram ~2.700 widgets
#: e ~2 s travados a cada troca de tema (medido; ate reaplicar a MESMA folha
#: custava o mesmo). Por isso o tema mora na folha de cada janela e de cada
#: regiao do Hub, e a da aplicacao so cuida do que nao tem janela nenhuma da
#: plataforma em cima: a dica de ferramenta. As cores dela vem da paleta, que
#: troca de graca.
FOLHA_DA_APLICACAO = """QToolTip {
    background-color: palette(tooltip-base);
    color: palette(tooltip-text);
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 600;
}"""


class ThemeManager(QObject):
    """Tema da plataforma. O Hub troca aqui; os aplicativos escutam.

    Trocar de tema aqui so troca a paleta e avisa: quem pinta cada janela e
    ela mesma (`apply_window_theme`, ou o Hub regiao por regiao).
    """

    changed = Signal(object)  # Palette

    def __init__(self, app: QApplication, mode: str = MODO_ESCURO) -> None:
        super().__init__(app)
        self._app = app
        self._mode = MODO_ESCURO
        app.setStyle("Fusion")
        app.setStyleSheet(FOLHA_DA_APLICACAO)
        # depois da folha: por a folha da aplicacao repoe o Segoe nas classes
        aplicar_fonte(app)
        self.set_mode(mode)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> Palette:
        return palette_by_name(self._mode)

    def set_mode(self, mode: str) -> Palette:
        mode = mode if mode in PALETTES else MODO_ESCURO
        self._mode = mode
        p = self.palette
        set_current_palette(p)
        paleta_qt = qt_palette(p)
        self._app.setPalette(paleta_qt)
        QToolTip.setPalette(paleta_qt)
        self.changed.emit(p)
        from . import chrome

        chrome.pintar_abertas()
        return p

    def toggle(self) -> Palette:
        return self.set_mode(MODO_CLARO if self._mode == MODO_ESCURO else MODO_ESCURO)


def apply_theme(app: QApplication, mode: str = MODO_ESCURO) -> ThemeManager:
    """Atalho: prepara a aplicacao e devolve o gerenciador de tema."""
    return ThemeManager(app, mode)
