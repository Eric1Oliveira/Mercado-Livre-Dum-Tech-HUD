"""Prepara a foto do produto antes de ir para o banco.

A foto vem do celular (4000 px, 5 MB) ou da internet (qualquer formato). Aqui
ela vira algo do tamanho que a tela usa: no maximo LADO_MAXIMO px, JPEG (ou PNG
quando tem fundo transparente). Fica com dezenas de KB - mil produtos com foto
nao pesam no backup.

Foto de celular guarda "estou de lado" no EXIF; `setAutoTransform` endireita,
senao a capinha aparece deitada no balcao.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QImageReader

from .models import EstoqueError

#: maior lado da imagem gravada - sobra para a foto grande do balcao
LADO_MAXIMO = 640
#: lado da miniatura quadrada das listas (desenhada a 28-32 px, nitida em 200%)
LADO_MINIATURA = 96
#: arquivo maior que isso nem e aberto (nao e foto de produto)
ARQUIVO_MAXIMO = 30 * 1024 * 1024
QUALIDADE_JPEG = 85

#: o que a janela de escolher arquivo oferece
FILTRO = "Imagens (*.jpg *.jpeg *.png *.webp *.bmp *.gif)"


def preparar(caminho: str | Path) -> bytes:
    """Le o arquivo, endireita, reduz e devolve os bytes prontos para gravar."""
    arquivo = Path(caminho)
    try:
        tamanho = arquivo.stat().st_size
    except OSError as exc:
        raise EstoqueError("Não consegui abrir esse arquivo.") from exc
    if tamanho > ARQUIVO_MAXIMO:
        raise EstoqueError("Arquivo grande demais para uma foto de produto (máximo 30 MB).")

    leitor = QImageReader(str(arquivo))
    leitor.setAutoTransform(True)
    imagem = leitor.read()
    if imagem.isNull():
        raise EstoqueError("Esse arquivo não é uma imagem que eu consiga abrir. Use JPG ou PNG.")
    return reduzir(imagem)


def reduzir(imagem: QImage) -> bytes:
    if max(imagem.width(), imagem.height()) > LADO_MAXIMO:
        imagem = imagem.scaled(
            LADO_MAXIMO, LADO_MAXIMO,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
    return _codificar(imagem)


def miniatura_de(dados: bytes) -> bytes:
    """Recorte quadrado do centro da foto, no tamanho das listas."""
    imagem = QImage.fromData(dados)
    if imagem.isNull():
        raise EstoqueError("Não consegui preparar essa imagem. Tente outra.")
    imagem = imagem.scaled(
        LADO_MINIATURA, LADO_MINIATURA,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
    )
    x = (imagem.width() - LADO_MINIATURA) // 2
    y = (imagem.height() - LADO_MINIATURA) // 2
    return _codificar(imagem.copy(x, y, LADO_MINIATURA, LADO_MINIATURA))


def _codificar(imagem: QImage) -> bytes:
    transparente = imagem.hasAlphaChannel()
    if not transparente:
        imagem = imagem.convertToFormat(QImage.Format.Format_RGB888)

    dados = QByteArray()
    buffer = QBuffer(dados)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = imagem.save(buffer, "PNG" if transparente else "JPEG", -1 if transparente else QUALIDADE_JPEG)
    buffer.close()
    if not ok or dados.isEmpty():
        raise EstoqueError("Não consegui preparar essa imagem. Tente outra.")
    return bytes(dados.data())
