"""Ver no celular: o QR que conecta o telefone do dono ao Hub.

O MESMO GESTO DO WHATSAPP WEB
    O Hub mostra um QR, o dono aponta a camera e pronto - sem baixar
    aplicativo, sem senha nova. O QR vale 5 minutos e uma leitura so; depois
    disso o celular fica com um acesso proprio, que se desliga aqui mesmo em
    "Desconectar".

A JANELA SE ACOMPANHA SOZINHA
    Enquanto esta aberta, pergunta ao servidor a cada poucos segundos quais
    celulares estao conectados. Quando entra um novo, ela avisa e o Hub manda
    o resumo na hora - o celular nao abre vazio.
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...core.celular import CelularError, CelularService
from ...ui import format as fmt
from ...ui import tasks
from ...ui.theme import Space, apply_window_theme, palette_for
from ...ui.widgets.buttons import Button
from ...ui.widgets.common import IconBadge, label, repolish, separator
from ...ui.widgets.qr import pixmap as qr_pixmap

LARGURA = 560
LADO_QR = 212
#: de quanto em quanto tempo a janela confere se o celular ja leu o QR
CONFERIR_MS = 3000

PASSOS = (
    "Abra a câmera do celular (iPhone ou Android).",
    "Aponte para o código ao lado e toque no link que aparecer.",
    "Pronto. Para voltar depois, use o atalho que a página ensina a criar.",
)


class CelularDialog(QDialog):
    """QR de pareamento + a lista dos celulares conectados."""

    #: quantos celulares estao conectados agora (o Hub liga/desliga o envio)
    aparelhos_mudaram = Signal(int)

    def __init__(self, service: CelularService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._expira: datetime | None = None
        self._conhecidos: set[str] | None = None
        self._conferindo = False
        self._fechada = False

        self.setWindowTitle("Ver no celular")
        self.setModal(True)
        self.setFixedWidth(LARGURA)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 22)
        raiz.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("phone", "accent", size=42, radius=13), 0, Qt.AlignmentFlag.AlignTop)
        cabeca = QVBoxLayout()
        cabeca.setSpacing(2)
        cabeca.addWidget(label("Seu negócio no celular", "title"))
        sub = label("Vendas, contas, ordens e agenda de onde você estiver. Só leitura: "
                    "nada muda no computador pelo celular.", "muted")
        sub.setWordWrap(True)
        cabeca.addWidget(sub)
        topo.addLayout(cabeca, 1)
        raiz.addLayout(topo)

        meio = QHBoxLayout()
        meio.setSpacing(Space.lg)
        # o QR fica sempre preto no branco (ver ui/widgets/qr.py)
        self.quadro = QLabel()
        self.quadro.setFixedSize(LADO_QR + 20, LADO_QR + 20)
        self.quadro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quadro.setStyleSheet("background:#FFFFFF; border-radius:14px; color:#555; font-size:12px;"
                                  f"border:1px solid {palette_for(parent).border};")
        self.quadro.setWordWrap(True)
        meio.addWidget(self.quadro, 0, Qt.AlignmentFlag.AlignTop)

        passos = QVBoxLayout()
        passos.setSpacing(Space.sm)
        for numero, texto in enumerate(PASSOS, 1):
            linha = QHBoxLayout()
            linha.setSpacing(Space.sm)
            bolinha = label(str(numero), "section")
            bolinha.setFixedWidth(16)
            linha.addWidget(bolinha, 0, Qt.AlignmentFlag.AlignTop)
            passo = label(texto, "body")
            passo.setWordWrap(True)
            linha.addWidget(passo, 1)
            passos.addLayout(linha)
        passos.addStretch(1)
        self.validade = label("", "dim")
        passos.addWidget(self.validade)
        self.botao_novo = Button("Gerar outro código", "refresh", "ghost")
        self.botao_novo.setAutoDefault(False)
        self.botao_novo.clicked.connect(self.gerar)
        passos.addWidget(self.botao_novo, 0, Qt.AlignmentFlag.AlignLeft)
        meio.addLayout(passos, 1)
        raiz.addLayout(meio)
        raiz.addSpacing(Space.xs)

        self.recado = label("", "muted")
        self.recado.setWordWrap(True)
        self.recado.setVisible(False)
        raiz.addWidget(self.recado)

        raiz.addWidget(separator())
        raiz.addWidget(label("Celulares conectados", "section"))
        self.lista = QVBoxLayout()
        self.lista.setSpacing(Space.xs)
        raiz.addLayout(self.lista)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        fechar = Button("Fechar", "", "primary")
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)
        botoes.addWidget(fechar)
        raiz.addLayout(botoes)

        self.relogio = QTimer(self)
        self.relogio.setInterval(1000)
        self.relogio.timeout.connect(self._passar_segundo)
        self.conferir = QTimer(self)
        self.conferir.setInterval(CONFERIR_MS)
        self.conferir.timeout.connect(self._conferir_aparelhos)

        apply_window_theme(self, palette_for(parent))
        self._desenhar_aparelhos([])
        self.gerar()
        self._conferir_aparelhos()
        self.conferir.start()

    # ----------------------------------------------------------------- QR
    def gerar(self) -> None:
        self.botao_novo.setEnabled(False)
        self.relogio.stop()
        self.quadro.clear()
        self.quadro.setText("Gerando o código...")
        self.validade.setText("")
        tasks.executar(self, self.service.iniciar, self._gerou, self._falhou_gerar)

    def _gerou(self, resposta: dict) -> None:
        if self._fechada:
            return
        self.botao_novo.setEnabled(True)
        self.quadro.setPixmap(qr_pixmap(resposta["link"], LADO_QR))
        try:
            self._expira = datetime.fromisoformat(str(resposta.get("expira_em")))
        except ValueError:
            self._expira = None
        self._dizer("")
        self._passar_segundo()
        self.relogio.start()

    def _falhou_gerar(self, erro: Exception) -> None:
        if self._fechada:
            return
        self.botao_novo.setEnabled(True)
        self.quadro.clear()
        self.quadro.setText("Sem código agora")
        self._dizer(str(erro) if isinstance(erro, CelularError) else
                    "Não foi possível gerar o código. Tente de novo.", "danger")

    def _passar_segundo(self) -> None:
        if self._expira is None:
            self.validade.setText("O código vale por 5 minutos.")
            return
        faltam = int((self._expira - datetime.now(timezone.utc)).total_seconds())
        if faltam <= 0:
            self.relogio.stop()
            self.quadro.clear()
            self.quadro.setText("Este código venceu.\nGere outro.")
            self.validade.setText("")
            return
        self.validade.setText(f"Vale por mais {faltam // 60}:{faltam % 60:02d}  ·  uma leitura só")

    # ---------------------------------------------------------- aparelhos
    def _conferir_aparelhos(self) -> None:
        if self._conferindo or self._fechada:
            return
        self._conferindo = True
        tasks.executar(self, self.service.aparelhos, self._chegaram, self._nao_conferiu)

    def _nao_conferiu(self, _erro: Exception) -> None:
        self._conferindo = False  # a proxima volta tenta de novo; o QR ja avisou o erro

    def _chegaram(self, aparelhos: list[dict]) -> None:
        self._conferindo = False
        if self._fechada:
            return
        ids = {str(a.get("id")) for a in aparelhos}
        if self._conhecidos is not None and ids - self._conhecidos:
            novo = next(a for a in aparelhos if str(a.get("id")) in ids - self._conhecidos)
            self._dizer(f"Pronto! {novo.get('nome') or 'O celular'} está conectado. "
                        "Os dados já estão indo para lá.", "success")
            self.gerar()  # o QR lido nao vale mais: ja deixa outro pronto
        if ids != self._conhecidos:
            self._conhecidos = ids
            self._desenhar_aparelhos(aparelhos)
            self.aparelhos_mudaram.emit(len(aparelhos))

    def _desenhar_aparelhos(self, aparelhos: list[dict]) -> None:
        while self.lista.count():
            item = self.lista.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not aparelhos:
            self.lista.addWidget(label("Nenhum ainda. Leia o código acima com o celular.", "dim"))
            return
        for aparelho in aparelhos:
            self.lista.addWidget(self._linha_aparelho(aparelho))

    def _linha_aparelho(self, aparelho: dict) -> QFrame:
        linha = QFrame()
        caixa = QHBoxLayout(linha)
        caixa.setContentsMargins(0, 2, 0, 2)
        caixa.setSpacing(Space.sm)
        caixa.addWidget(IconBadge("phone", "muted", size=30, radius=9))
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addWidget(label(aparelho.get("nome") or "Celular", "body"))
        visto = aparelho.get("ultimo_acesso") or aparelho.get("criado_em")
        textos.addWidget(label(f"Visto por último: {fmt.data_hora_curta(visto)}", "dim"))
        caixa.addLayout(textos, 1)
        botao = Button("Desconectar", "", "ghost")
        botao.setAutoDefault(False)
        botao.clicked.connect(lambda _=False, a=aparelho, b=botao: self._desconectar(a, b))
        caixa.addWidget(botao)
        return linha

    def _desconectar(self, aparelho: dict, botao: Button) -> None:
        botao.setEnabled(False)
        botao.setText("Desconectando...")

        def pronto(_=None) -> None:
            if self._fechada:
                return
            self._dizer(f"{aparelho.get('nome') or 'O celular'} foi desconectado e não vê mais nada.", "muted")
            self._conferir_aparelhos()

        def falhou(erro: Exception) -> None:
            if self._fechada:
                return
            botao.setEnabled(True)
            botao.setText("Desconectar")
            self._dizer(str(erro), "danger")

        tasks.executar(self, lambda: self.service.revogar(str(aparelho.get("id"))), pronto, falhou)

    # -------------------------------------------------------------- resto
    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.recado.setText(texto)
        self.recado.setVisible(bool(texto))
        self.recado.setProperty("tone", tom)
        repolish(self.recado)

    def done(self, resultado: int) -> None:
        self._fechada = True
        self.relogio.stop()
        self.conferir.stop()
        super().done(resultado)
