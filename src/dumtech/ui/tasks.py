"""Executa uma tarefa demorada fora da interface.

Usado nas chamadas de licenca: enquanto o Hub fala com a internet, a janela
continua respondendo. O resultado volta pela thread da interface, entao os
callbacks podem mexer nos widgets normalmente.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Sinais(QObject):
    concluido = Signal(object)
    falhou = Signal(object)


class _Trabalho(QRunnable):
    def __init__(self, funcao: Callable[[], Any], sinais: _Sinais) -> None:
        super().__init__()
        self._funcao = funcao
        self._sinais = sinais

    def run(self) -> None:  # executado na thread secundaria
        try:
            resultado = self._funcao()
        except Exception as erro:  # noqa: BLE001 - o erro e entregue ao chamador
            self._sinais.falhou.emit(erro)
        else:
            self._sinais.concluido.emit(resultado)


def executar(
    parent: QObject,
    funcao: Callable[[], Any],
    ao_concluir: Callable[[Any], None],
    ao_falhar: Callable[[Exception], None],
) -> None:
    """Roda `funcao` em segundo plano e devolve o resultado na interface."""
    sinais = _Sinais(parent)  # o parent mantem o objeto vivo ate o fim
    sinais.concluido.connect(ao_concluir)
    sinais.falhou.connect(ao_falhar)
    QThreadPool.globalInstance().start(_Trabalho(funcao, sinais))
