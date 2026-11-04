"""Ponto de entrada do DumTech Hub."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QLockFile, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .core.config import Settings
from .core.paths import get_paths
from .hub.main_window import HubWindow
from .ui import erros
from .ui.theme import MODO_ESCURO, ThemeManager


#: o log nao pode crescer para sempre na maquina do cliente
LOG_MAXIMO = 2 * 1024 * 1024
LOG_COPIAS = 3


def setup_logging() -> None:
    """Grava erros em arquivo para facilitar o suporte ao cliente.

    Arquivo rotativo: um programa que roda por anos nao pode deixar um log de
    centenas de megabytes na maquina de quem comprou.
    """
    paths = get_paths()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                paths.log_file, maxBytes=LOG_MAXIMO, backupCount=LOG_COPIAS,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _traduzir_qt(app: QApplication) -> None:
    """Botoes dos dialogos do proprio Qt em portugues.

    Sem isso a caixa de confirmacao pergunta em portugues e responde "Yes/No".
    Se a traducao nao estiver disponivel, segue em ingles - nao e motivo para
    o programa deixar de abrir.
    """
    tradutor = QTranslator(app)
    pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tradutor.load(QLocale("pt_BR"), "qtbase", "_", pasta):
        app.installTranslator(tradutor)
        app._dt_tradutor = tradutor  # segura a referencia viva
    else:
        logging.getLogger(__name__).info("Traducao pt_BR do Qt nao encontrada")


def _windows_taskbar_identity() -> None:
    """Faz o Windows tratar o Hub como programa proprio na barra de tarefas."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DumTech.Hub")
    except Exception:  # pragma: no cover - detalhe cosmetico
        pass


def travar_instancia(pasta: Path, espera_ms: int = 3000) -> QLockFile | None:
    """Garante um Hub so por usuario; None quando outro ja esta aberto.

    Dois Hubs sobre os mesmos bancos gravam por cima um do outro: o caixa de um
    nao ve o do outro, e restaurar um backup com o segundo aberto trava no meio.
    A espera cobre a atualizacao, em que o Hub velho ainda esta saindo quando o
    novo abre. Quem cai sem soltar a trava nao bloqueia ninguem: o Qt confere
    se o dono ainda existe.
    """
    trava = QLockFile(str(pasta / "hub.lock"))
    trava.setStaleLockTime(0)
    return trava if trava.tryLock(espera_ms) else None


def run() -> int:
    setup_logging()
    logging.getLogger(__name__).info("Iniciando DumTech Hub %s", __version__)
    _windows_taskbar_identity()

    app = QApplication(sys.argv)
    # antes de qualquer tela: erro que aparece e melhor que erro que some
    erros.instalar(__version__, get_paths().log_file)
    _traduzir_qt(app)
    app.setApplicationName("DumTech Hub")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("DumTech")

    trava = travar_instancia(get_paths().root)
    if trava is None:
        QMessageBox.information(
            None, "DumTech Hub",
            "O DumTech Hub já está aberto neste computador. Procure a janela dele "
            "na barra de tarefas.",
        )
        return 0

    settings = Settings()
    theme = ThemeManager(app, str(settings.get("hub", "theme", MODO_ESCURO)))

    window = HubWindow(settings=settings, theme=theme)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
