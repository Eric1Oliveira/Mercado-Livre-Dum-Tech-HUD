"""Tela de backup: onde o cliente protege - ou recupera - o trabalho dele.

A tela precisa ser honesta sobre uma coisa: copia guardada no mesmo HD nao
salva de HD queimado. Por isso o aviso de escolher pendrive ou pasta de nuvem
fica em cima, e nao escondido numa nota de rodape.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...core import backup
from ...core.backup import Backup, BackupError
from ...ui import format as fmt
from ...ui.theme import Space
from ...ui.widgets.buttons import Button
from ...ui.widgets.rolagem import Rolagem
from ...ui.widgets.common import Card, IconBadge, label, repolish, separator, tone_label
from ...ui.widgets.table import DIREITA, DataTable


def tamanho_texto(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / 1024 / 1024:.1f} MB".replace(".", ",")
    return f"{max(bytes_ // 1024, 1)} KB"


class BackupView(QWidget):
    """Fazer copia, escolher onde guardar e restaurar."""

    #: o programa precisa fechar para carregar os dados restaurados
    restaurado = Signal()

    def __init__(self, settings, paths=None, versao: str = "", parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.paths = paths
        self.versao = versao
        self.copias: list[Backup] = []

        # sem margem nem titulo proprios: esta tela e uma secao de Configuracoes
        # a pagina inteira rola: em monitor pequeno isto vira uma barra
        # de rolagem fina em vez de um pedaco da tela faltando
        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        corpo = QWidget()
        fora.addWidget(Rolagem(corpo), 1)
        raiz = QVBoxLayout(corpo)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(Space.lg)
        raiz.addWidget(
            label("Tudo que voce digitou vive neste computador. Guarde uma copia.",
                  "subtitle")
        )

        raiz.addWidget(self._card_pasta())
        raiz.addWidget(self._card_fora())
        raiz.addWidget(self._card_copias(), 1)
        raiz.addLayout(self._acoes())

        self.refresh()

    # ------------------------------------------------------------------ pedacos
    def _card_pasta(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("shield", "accent", size=44, radius=13))

        texto = QVBoxLayout()
        texto.setSpacing(1)
        texto.addWidget(label("Onde as copias sao guardadas", "section"))
        self.caminho = label("", "muted")
        self.caminho.setWordWrap(True)
        texto.addWidget(self.caminho)
        topo.addLayout(texto, 1)

        trocar = Button("Escolher pasta", "external")
        trocar.clicked.connect(self._escolher_pasta)
        topo.addWidget(trocar)
        card.body.addLayout(topo)

        # o aviso que impede a falsa sensacao de seguranca
        self.alerta = tone_label("", "warning", "strong")
        self.alerta.setWordWrap(True)
        card.body.addWidget(self.alerta)

        card.body.addWidget(separator())
        self.automatico = QCheckBox(
            "Fazer uma copia sozinho ao abrir o programa (uma por dia)"
        )
        self.automatico.stateChanged.connect(self._salvar_preferencia)
        card.body.addWidget(self.automatico)
        return card

    def _card_fora(self) -> Card:
        """A copia que sobrevive ao computador.

        Copia guardada so aqui morre junto com o HD, com a formatacao e com o
        ransomware. Uma pasta que a nuvem sincroniza (ou um pendrive) resolve
        isso sem servidor nenhum e sem custo.
        """
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.md)

        topo = QHBoxLayout()
        topo.setSpacing(Space.md)
        topo.addWidget(IconBadge("box", "success", size=44, radius=13))
        texto = QVBoxLayout()
        texto.setSpacing(1)
        texto.addWidget(label("Copia fora deste computador", "section"))
        self.caminho_fora = label("", "muted")
        self.caminho_fora.setWordWrap(True)
        texto.addWidget(self.caminho_fora)
        topo.addLayout(texto, 1)

        self.botao_fora = Button("Escolher pasta", "external")
        self.botao_fora.clicked.connect(self._escolher_pasta_fora)
        topo.addWidget(self.botao_fora)
        self.botao_tirar_fora = Button("Tirar", "close", "ghost")
        self.botao_tirar_fora.clicked.connect(self._tirar_pasta_fora)
        topo.addWidget(self.botao_tirar_fora)
        card.body.addLayout(topo)

        self.recado_fora = label("", "dim")
        self.recado_fora.setWordWrap(True)
        card.body.addWidget(self.recado_fora)
        return card

    def _card_copias(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.addWidget(label("Copias guardadas", "section"))
        card.body.addWidget(separator())
        self.tabela = DataTable(["Quando", "Origem", "Aplicativos", "Tamanho"])
        self.tabela.set_empty_message(
            "Nenhuma copia ainda. Clique em 'Fazer backup agora'."
        )
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        card.body.addWidget(self.tabela, 1)
        return card

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(Space.sm)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        linha.addWidget(self.aviso, 1)

        self.botao_abrir_pasta = Button("Abrir a pasta", "external", "ghost")
        self.botao_abrir_pasta.clicked.connect(self._abrir_pasta)
        linha.addWidget(self.botao_abrir_pasta)

        self.botao_restaurar = Button("Restaurar esta copia", "back")
        self.botao_restaurar.clicked.connect(self._restaurar)
        linha.addWidget(self.botao_restaurar)

        self.botao_backup = Button("Fazer backup agora", "shield", "primary")
        self.botao_backup.setMinimumHeight(38)
        self.botao_backup.clicked.connect(self._fazer_backup)
        linha.addWidget(self.botao_backup)
        return linha

    # ------------------------------------------------------------------- dados
    @property
    def pasta(self) -> Path:
        guardada = self.settings.get("backup", "pasta", "")
        return Path(guardada) if guardada else backup.pasta_padrao(self.paths)

    @property
    def pasta_fora(self) -> Path | None:
        guardada = self.settings.get("backup", "pasta_fora", "")
        return Path(guardada) if guardada else None

    def _refresh_fora(self) -> None:
        fora = self.pasta_fora
        self.botao_tirar_fora.setVisible(fora is not None)
        self.botao_fora.setText("  Trocar pasta" if fora else "  Escolher pasta")
        if fora is None:
            sugestao = backup.nuvens_encontradas()
            self.caminho_fora.setText("Nenhuma - a copia existe so neste computador.")
            self.recado_fora.setText(
                "Se o HD queimar ou a maquina for formatada, a copia vai junto. "
                "Escolha uma pasta que o "
                + (f"{sugestao[0].name} sincroniza (achamos {sugestao[0]}) "
                   if sugestao else "OneDrive, o Google Drive ou o Dropbox sincroniza ")
                + "ou um pendrive: cada backup e duplicado para la sozinho."
            )
            return
        self.caminho_fora.setText(str(fora))
        quando = str(self.settings.get("backup", "fora_em", "") or "")
        # o zip leva os dados dos SEUS clientes: quem puder abrir a pasta, le tudo
        self.recado_fora.setText(
            (f"Ultima copia enviada em {quando}. " if quando
             else "A proxima copia ja vai para la tambem. ")
            + "A copia leva os dados dos seus clientes: use uma pasta particular "
              "(nao compartilhada) e mantenha a criptografia do Windows ligada."
        )

    def enviar_para_fora(self, copia) -> str:
        """Duplica a copia na pasta de fora. Devolve o recado (vazio = nada a fazer)."""
        fora = self.pasta_fora
        if fora is None:
            return ""
        try:
            backup.copiar_para_fora(copia, fora)
        except BackupError as erro:
            return str(erro)
        self.settings.set("backup", "fora_em", datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.settings.save()
        return ""

    def refresh(self) -> None:
        pasta = self.pasta
        self.caminho.setText(str(pasta))
        self._refresh_fora()
        self.automatico.blockSignals(True)
        self.automatico.setChecked(bool(self.settings.get("backup", "automatico", True)))
        self.automatico.blockSignals(False)

        # copia no mesmo disco nao salva de disco queimado - e preciso dizer isso
        interna = self.paths is not None and _dentro(pasta, self.paths.root)
        if interna:
            self.alerta.setText(
                "Estas copias estao no mesmo computador que os dados. Se o HD "
                "queimar ou a maquina for formatada, elas somem junto. Escolha "
                "um pendrive, um HD externo ou uma pasta do Google Drive / OneDrive."
            )
        else:
            self.alerta.setText("")
        self.alerta.setVisible(bool(self.alerta.text()))

        self.copias = backup.listar(pasta)
        self.tabela.fill(
            [
                [
                    self.tabela.cell(self._quando(copia), bold=True),
                    self.tabela.cell(
                        "Automatico" if copia.automatico else "Feito por voce",
                        tone="muted" if copia.automatico else "accent",
                    ),
                    self.tabela.cell(self._aplicativos(copia)),
                    self.tabela.cell(tamanho_texto(copia.tamanho), DIREITA),
                ]
                for copia in self.copias
            ],
            {0: 190, 1: 150, 3: 120},
        )
        self._atualizar_acoes()

    @staticmethod
    def _quando(copia: Backup) -> str:
        momento = copia.momento
        return fmt.data_hora(momento.isoformat()) if momento else copia.arquivo.name

    @staticmethod
    def _aplicativos(copia: Backup) -> str:
        nomes = [Path(b).stem for b in copia.bancos]
        return ", ".join(nomes) if nomes else "-"

    def selecionada(self) -> Backup | None:
        linha = self.tabela.currentRow()
        return self.copias[linha] if 0 <= linha < len(self.copias) else None

    def _atualizar_acoes(self) -> None:
        self.botao_restaurar.setEnabled(self.selecionada() is not None)
        self.botao_abrir_pasta.setEnabled(self.pasta.exists())

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------- acoes
    def _salvar_preferencia(self) -> None:
        self.settings.set("backup", "automatico", self.automatico.isChecked())
        self.settings.save()
        self._dizer(
            "Copia automatica ligada." if self.automatico.isChecked()
            else "Copia automatica desligada. Lembre de fazer o backup na mao."
        )

    def _escolher_pasta_fora(self) -> None:
        sugestao = backup.nuvens_encontradas()
        inicio = str(self.pasta_fora or (sugestao[0] if sugestao else Path.home()))
        escolhida = QFileDialog.getExistingDirectory(
            self, "Pasta da nuvem ou pendrive para a copia de fora", inicio
        )
        if not escolhida:
            return
        if _dentro(Path(escolhida), self.pasta):
            self._dizer("Escolha uma pasta FORA daqui - senao as duas copias morrem juntas.",
                        "danger")
            return
        self.settings.set("backup", "pasta_fora", escolhida)
        self.settings.save()
        self.refresh()
        self._dizer(f"Cada copia passa a ser duplicada em {escolhida}.", "success")

    def _tirar_pasta_fora(self) -> None:
        self.settings.set("backup", "pasta_fora", "")
        self.settings.save()
        self.refresh()
        self._dizer("A copia de fora foi desligada. As copias ficam so neste computador.")

    def _escolher_pasta(self) -> None:
        escolhida = QFileDialog.getExistingDirectory(
            self, "Onde guardar as copias de seguranca", str(self.pasta)
        )
        if not escolhida:
            return
        self.settings.set("backup", "pasta", escolhida)
        self.settings.save()
        self.refresh()
        self._dizer(f"As copias passam a ser guardadas em {escolhida}.", "success")

    def _abrir_pasta(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pasta)))

    def _fazer_backup(self) -> None:
        try:
            copia = backup.criar(self.pasta, self.paths, versao=self.versao)
        except BackupError as erro:
            self.refresh()
            self._dizer(str(erro), "danger")
            return
        problema = self.enviar_para_fora(copia)
        self.refresh()
        if problema:
            self._dizer(problema, "warning")
            return
        destino = " (e na pasta de fora)" if self.pasta_fora else ""
        self._dizer(
            f"Copia gravada: {copia.arquivo.name} ({tamanho_texto(copia.tamanho)}){destino}.",
            "success",
        )

    def _restaurar(self) -> None:
        copia = self.selecionada()
        if copia is None:
            return

        resposta = QMessageBox.question(
            self,
            "Restaurar backup",
            f"Isto troca TODOS os dados de agora pelos de "
            f"{self._quando(copia)}.\n\n"
            "Uma copia do estado atual sera guardada antes, por seguranca.\n"
            "O programa precisa ser fechado e aberto de novo.\n\nContinuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.restaurar_agora(copia)

    def restaurar_agora(self, copia: Backup) -> bool:
        """Separado do dialogo para poder ser testado sem abrir caixa nenhuma."""
        try:
            # rede de seguranca: se a copia escolhida for a errada, ainda da
            # para voltar para o estado de agora
            backup.criar(self.pasta, self.paths, versao=self.versao)
        except BackupError:
            pass  # sem dados para copiar: seguir mesmo assim

        self.restaurado.emit()  # quem tem banco aberto fecha agora
        try:
            bancos = backup.restaurar(copia.arquivo, self.paths)
        except BackupError as erro:
            self._dizer(str(erro), "danger")
            return False

        self.refresh()
        self._dizer(
            f"{fmt.contagem(len(bancos), 'banco')} restaurado(s). "
            "Feche e abra o DumTech Hub para usar os dados recuperados.",
            "success",
        )
        return True


def _dentro(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.resolve().relative_to(pasta.resolve())
    except (ValueError, OSError):
        return False
    return True
