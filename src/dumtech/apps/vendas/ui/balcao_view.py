"""O balcao: a tela em que a venda acontece.

Aqui nao existe formulario. O campo de bipe fica sempre com o foco, o item
entra na lista, o TOTAL cresce e F12 recebe. Nada e gravado ate o pagamento
fechar - desistir da venda nao deixa rastro no banco.

Teclas: F2 volta para o bipe, F4 desconto, F12 recebe, Delete tira a linha.

Produto com foto no Estoque aparece com ela: grande, ao lado do bipe (o ultimo
produto achado), e pequena na lista da venda. Foto e enfeite - se nao der para
le-la, a venda segue sem ela.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ....ui import format as fmt
from ....ui import icons
from ....ui.theme import Space, palette_for
from ....ui.widgets import form
from ....ui.widgets.buttons import Button
from ....ui.widgets.busca_catalogo import BuscaCatalogo
from ....ui.widgets.common import Card, label, repolish, tone_label
from ....ui.widgets.foto import FotoProduto, miniatura, miniatura_vazia
from ....ui.widgets.table import DIREITA, DataTable
from .. import financeiro
from ..models import ItemVenda, Venda, VendaError, quantidade_texto
from ..repository import VendasRepository
from .pagamento_dialog import PagamentoDialog

logger = logging.getLogger(__name__)

COLUNAS = ["Item", "Quantidade", "Valor unitário", "Total"]
#: foto do ultimo produto achado (a altura do campo + a linha "saldo")
FOTO = 80
#: foto pequena na lista da venda (a linha da tabela tem 40)
MINIATURA = 28


class BalcaoView(QWidget):
    """PDV: monta a venda, recebe e da baixa no estoque."""

    data_changed = Signal()

    def __init__(
        self,
        repository: VendasRepository,
        clientes: list[str] | None = None,
        parent: QWidget | None = None,
        contas=None,
        empresa=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.clientes = clientes or []
        #: ponte com o Financeiro; None quando a licenca nao o libera
        self.contas = contas
        #: de onde sai a chave Pix do QR Code; o Hub troca quando ela muda
        self.empresa = empresa
        self.itens: list[ItemVenda] = []
        #: ("imagem" | "miniatura", produto_id) -> bytes ou None; le uma vez so
        self._imagens: dict[tuple[str, int], bytes | None] = {}
        self._foto_de = 0

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 24)
        raiz.setSpacing(Space.lg)

        raiz.addLayout(self._cabecalho())
        raiz.addWidget(self._card_item())

        self.tabela = DataTable(COLUNAS)
        self.tabela.set_empty_message("Bipe ou digite o primeiro item da venda.")
        self.tabela.setIconSize(QSize(MINIATURA, MINIATURA))
        self.tabela.itemSelectionChanged.connect(self._atualizar_acoes)
        raiz.addWidget(self.tabela, 1)

        raiz.addWidget(self._card_fechamento())

        self._atalhos()
        self.refresh()

    # -------------------------------------------------------------- cabecalho
    def _cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        titulos.addWidget(label("Balcão", "title"))
        titulos.addWidget(label("Bipe, confira e receba", "subtitle"))
        linha.addLayout(titulos)
        linha.addStretch(1)

        self.estado_caixa = tone_label("", "muted", "strong")
        self.estado_caixa.setAlignment(Qt.AlignmentFlag.AlignRight)
        linha.addWidget(self.estado_caixa, 0, Qt.AlignmentFlag.AlignVCenter)
        return linha

    def _card_item(self) -> Card:
        card = Card(padding=Space.lg)
        conteudo = QHBoxLayout()
        conteudo.setSpacing(Space.md)
        # a altura da foto vale sempre: ela aparecer e sumir nao sacode a lista
        conteudo.addStrut(FOTO)
        self.foto = FotoProduto(FOTO, parent=self)
        self.foto.hide()
        conteudo.addWidget(self.foto, 0, Qt.AlignmentFlag.AlignTop)
        campos = QVBoxLayout()
        campos.setSpacing(Space.sm)
        conteudo.addLayout(campos, 1)
        card.body.addLayout(conteudo)

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)

        self.bipe = QLineEdit()
        self._acao_bipe = self.bipe.addAction(
            icons.icon("tag", palette_for(self).accent, 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.bipe.returnPressed.connect(self._localizar)
        self.bipe.textChanged.connect(self._digitou)
        linha.addWidget(form.campo("Produto", self.bipe), 5)

        self.quantidade = QDoubleSpinBox()
        self.quantidade.setRange(0, 9_999_999)
        self.quantidade.setDecimals(0)
        self.quantidade.setValue(1)
        self.quantidade.setMinimumWidth(100)
        linha.addWidget(form.campo("Quantidade", self.quantidade), 1)

        self.valor = form.dinheiro(0.0)
        # o campo de dinheiro so assume o numero quando perde o foco; o
        # Adicionar acompanha o que esta escrito, tecla a tecla
        self.valor.lineEdit().textChanged.connect(lambda _texto: self._atualizar_acoes())
        linha.addWidget(form.campo("Valor unitário", self.valor), 2)

        self.botao_adicionar = Button("Adicionar", "plus", "primary")
        self.botao_adicionar.clicked.connect(self._adicionar)
        linha.addWidget(form.campo(" ", self.botao_adicionar), 1)
        campos.addLayout(linha)

        self.achado = label("", "dim")
        campos.addWidget(self.achado)
        self._catalogado: object | None = None

        # a lista de produtos que aparece enquanto se digita. Ela nunca fica
        # com o Enter sem que alguem tenha apertado a seta - o leitor de
        # codigo de barras continua caindo no `_localizar` de sempre.
        self.busca = BuscaCatalogo(
            self.bipe, self.repository.catalogo if self.repository.tem_catalogo else None
        )
        self.busca.escolhido.connect(self._usar_produto)
        return card

    def _card_fechamento(self) -> Card:
        card = Card(padding=Space.lg)
        card.body.setSpacing(Space.md)

        linha = QHBoxLayout()
        linha.setSpacing(Space.md)
        self.cliente = form.sugestao("", "Consumidor", self.clientes)
        linha.addWidget(form.campo("Cliente (opcional)", self.cliente), 3)
        self.desconto = form.dinheiro(0.0)
        self.desconto.valueChanged.connect(self._atualizar_total)
        linha.addWidget(form.campo("Desconto", self.desconto), 1)
        linha.addStretch(2)

        totais = QVBoxLayout()
        totais.setSpacing(0)
        self.contagem = label("", "dim")
        self.contagem.setAlignment(DIREITA)
        totais.addWidget(self.contagem)
        self.total = tone_label(fmt.moeda(0), "accent", "metric")
        self.total.setAlignment(DIREITA)
        totais.addWidget(self.total)
        linha.addLayout(totais)
        card.body.addLayout(linha)

        acoes = QHBoxLayout()
        acoes.setSpacing(Space.sm)
        self.aviso = label("", "muted")
        self.aviso.setWordWrap(True)
        acoes.addWidget(self.aviso, 1)

        self.botao_remover = Button("Remover item", "trash")
        self.botao_remover.clicked.connect(self._remover)
        acoes.addWidget(self.botao_remover)

        self.botao_limpar = Button("Descartar venda", "close", "ghost")
        self.botao_limpar.clicked.connect(self._limpar)
        acoes.addWidget(self.botao_limpar)

        self.botao_receber = Button("Receber  (F12)", "money", "success")
        self.botao_receber.setMinimumHeight(42)
        self.botao_receber.clicked.connect(self.receber)
        acoes.addWidget(self.botao_receber)
        card.body.addLayout(acoes)
        return card

    def _atalhos(self) -> None:
        def atalho(sequencia: str, funcao) -> None:
            QShortcut(QKeySequence(sequencia), self, activated=funcao)

        atalho("F2", lambda: (self.bipe.setFocus(), self.bipe.selectAll()))
        atalho("F4", lambda: (self.desconto.setFocus(), self.desconto.selectAll()))
        atalho("F12", self.receber)
        atalho("Delete", self._remover)

    # ------------------------------------------------------------------- dados
    def refresh(self) -> None:
        caixa = self.repository.caixa_aberto()
        if caixa is None:
            self.estado_caixa.setText("Caixa fechado")
            self.estado_caixa.setProperty("tone", "muted")
        else:
            conferencia = self.repository.conferencia(caixa.id)
            self.estado_caixa.setText(
                f"Caixa aberto  ·  {fmt.moeda(conferencia.esperado)} na gaveta"
            )
            self.estado_caixa.setProperty("tone", "success")
        repolish(self.estado_caixa)

        if not self.repository.tem_catalogo:
            self.bipe.setPlaceholderText("Descreva o item vendido...")
            self.achado.setText(
                "Sem o DumTech Estoque, o item é digitado na hora e não baixa saldo."
            )
        else:
            self.bipe.setPlaceholderText("Bipe o código de barras ou digite o produto...")
        # a casca troca `self.clientes` quando alguem cadastra cliente; o campo
        # nasceu com a lista da abertura e so mostra a nova se receber de novo
        self.cliente.completer().definir(self.clientes)
        self._imagens.clear()  # a foto pode ter mudado no Estoque
        self._preencher()

    def _preencher(self) -> None:
        fotos = [
            miniatura(self._ler("miniatura", item.produto_id), MINIATURA) for item in self.itens
        ]
        # com alguma foto na venda, quem nao tem ganha o quadro vazio (o mesmo do
        # Estoque e da sugestao): os nomes continuam alinhados na mesma coluna
        tem_foto = any(foto is not None for foto in fotos)
        vazio = miniatura_vazia(MINIATURA, palette_for(self)) if tem_foto else None
        linhas = []
        for item, foto in zip(self.itens, fotos):
            nome = f"{item.codigo} · {item.descricao}" if item.codigo else item.descricao
            celula = self.tabela.cell(nome, bold=True)
            if tem_foto:
                celula.setIcon(QIcon(foto if foto is not None else vazio))
            linhas.append([
                celula,
                self.tabela.cell(item.quantidade_texto, DIREITA),
                self.tabela.cell(fmt.moeda(item.valor_unitario), DIREITA),
                self.tabela.cell(fmt.moeda(item.total), DIREITA, "accent", bold=True),
            ])
        self.tabela.fill(linhas, {1: 140, 2: 150, 3: 150})
        self._atualizar_total()

    # ------------------------------------------------------------------- foto
    def _ler(self, tipo: str, produto_id: int) -> bytes | None:
        """A foto inteira (`imagem`) ou o recorte das listas (`miniatura`)."""
        if not produto_id or not self.repository.tem_catalogo:
            return None
        chave = (tipo, produto_id)
        if chave not in self._imagens:
            ler = getattr(self.repository.catalogo, tipo, None)
            try:
                self._imagens[chave] = ler(produto_id) if ler else None
            except Exception:  # noqa: BLE001 - sem foto, a venda continua
                logger.exception("Nao foi possivel ler a foto do produto %s", produto_id)
                self._imagens[chave] = None
        return self._imagens[chave]

    def _mostrar_foto(self, produto_id: int = 0) -> None:
        """Foto grande do ultimo produto achado; some se ele nao tem foto."""
        tem = self.foto.set_imagem(self._ler("imagem", produto_id))
        self._foto_de = produto_id if tem else 0
        self.foto.setVisible(bool(self._foto_de))

    def _atualizar_total(self) -> None:
        venda = self._montar()
        self.total.setText(fmt.moeda(venda.total))
        quantidade = len(self.itens)
        if quantidade:
            plural = "item" if quantidade == 1 else "itens"
            texto = f"{quantidade} {plural}"
            if venda.desconto:
                texto += f"  ·  subtotal {fmt.moeda(venda.subtotal)}"
            self.contagem.setText(texto)
        else:
            self.contagem.setText("nenhum item")
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        tem_itens = bool(self.itens)
        self.botao_receber.setEnabled(tem_itens)
        self.botao_limpar.setEnabled(tem_itens)
        self.botao_remover.setEnabled(0 <= self.tabela.currentRow() < len(self.itens))
        self.botao_adicionar.setEnabled(
            bool(self.bipe.text().strip()) and self._valor_digitado() > 0
        )

    def _valor_digitado(self) -> float:
        """O valor escrito no campo, inclusive o que ainda nao saiu dele.

        `value()` so muda quando o campo perde o foco: era por isso que o
        Adicionar ficava apagado ate a pessoa trocar de aba e voltar.
        """
        return self.valor.valueFromText(self.valor.cleanText())

    def _montar(self) -> Venda:
        return Venda(
            cliente=self.cliente.text(),
            itens=list(self.itens),
            desconto=self.desconto.value(),
        )

    def _dizer(self, texto: str, tom: str = "muted") -> None:
        self.aviso.setText(texto)
        self.aviso.setProperty("tone", tom)
        repolish(self.aviso)

    # ------------------------------------------------------------------ item
    def _digitou(self, _texto: str = "") -> None:
        """Mexeu no campo depois de achar: o produto encontrado nao vale mais."""
        if self._catalogado is not None:
            self._catalogado = None
            self.achado.setText("")
        self._atualizar_acoes()

    def _localizar(self) -> None:
        termo = self.bipe.text().strip()
        if not termo:
            return
        if not self.repository.tem_catalogo:
            self.quantidade.setFocus()
            self.quantidade.selectAll()
            return

        item = self.repository.catalogo.buscar(termo)
        if item is None:
            self._catalogado = None
            self._mostrar_foto()
            self.achado.setText(
                f"'{termo}' não está no estoque. Informe o valor para vender avulso."
            )
            self.valor.setFocus()
            self.valor.selectAll()
            return

        self._usar_produto(item)

    def _usar_produto(self, item) -> None:
        """Preenche a linha com o produto do catalogo.

        Chegam aqui os dois caminhos: o Enter de sempre (inclusive o do leitor
        de codigo de barras) e a escolha na lista de sugestao.
        """
        self._catalogado = item
        self._mostrar_foto(item.produto_id)
        self.busca.fechar()
        self.bipe.blockSignals(True)
        self.bipe.setText(item.nome)
        self.bipe.blockSignals(False)
        self.quantidade.setDecimals(item.casas)
        self.quantidade.setValue(1)
        self.valor.setValue(item.preco)
        saldo = quantidade_texto(item.saldo, item.unidade, item.casas)
        self.achado.setText(f"{item.rotulo}   (saldo: {saldo})")
        self.quantidade.setFocus()
        self.quantidade.selectAll()
        self._atualizar_acoes()

    def _adicionar(self) -> None:
        # o clique pode chegar antes de o campo largar o foco: vale o que esta escrito
        self.valor.interpretText()
        self.quantidade.interpretText()
        descricao = self.bipe.text().strip()
        if not descricao:
            self._dizer("Informe o que está sendo vendido.", "danger")
            return
        if self.quantidade.value() <= 0:
            self._dizer("A quantidade precisa ser maior que zero.", "danger")
            return
        if self.valor.value() <= 0:
            self._dizer("Informe o valor do item.", "danger")
            return

        catalogado = self._catalogado
        item = ItemVenda(
            descricao=descricao,
            quantidade=self.quantidade.value(),
            valor_unitario=self.valor.value(),
            produto_id=getattr(catalogado, "produto_id", 0),
            codigo=getattr(catalogado, "codigo", ""),
            unidade=getattr(catalogado, "unidade", "UN"),
            casas=getattr(catalogado, "casas", 0),
        )
        # bipar o mesmo produto duas vezes soma, em vez de virar duas linhas
        for existente in self.itens:
            if item.do_estoque and existente.produto_id == item.produto_id:
                existente.quantidade += item.quantidade
                existente.valor_unitario = item.valor_unitario
                break
        else:
            self.itens.append(item)

        if item.do_estoque and catalogado is not None:
            vendido = sum(i.quantidade for i in self.itens if i.produto_id == item.produto_id)
            if vendido > catalogado.saldo:
                self._dizer(
                    f"Atenção: o estoque de '{item.descricao}' tem apenas "
                    f"{quantidade_texto(catalogado.saldo, item.unidade, item.casas)}. "
                    "A venda continua.",
                    "warning",
                )
            else:
                self._dizer("")
        else:
            self._dizer("")

        self._limpar_entrada()
        self._preencher()

    def _limpar_entrada(self) -> None:
        self._catalogado = None
        self.bipe.clear()
        self.achado.setText("")
        self.quantidade.setDecimals(0)
        self.quantidade.setValue(1)
        self.valor.setValue(0.0)
        self.bipe.setFocus()

    def _remover(self) -> None:
        linha = self.tabela.currentRow()
        if 0 <= linha < len(self.itens):
            item = self.itens.pop(linha)
            if item.produto_id and item.produto_id == self._foto_de:
                self._mostrar_foto()
            self._dizer(f"'{item.descricao}' saiu da venda.")
            self._preencher()

    def _limpar(self) -> None:
        self.itens.clear()
        self.cliente.clear()
        self.desconto.setValue(0.0)
        self._limpar_entrada()
        self._mostrar_foto()
        self._dizer("Venda descartada. Nada foi gravado.")
        self._preencher()

    # -------------------------------------------------------------- pagamento
    def receber(self) -> None:
        if not self.itens:
            self._dizer("Adicione um item antes de receber.", "danger")
            return

        venda = self._montar()
        dialogo = PagamentoDialog(
            venda.total,
            f"{len(self.itens)} item(ns)  ·  {self.cliente.text() or 'Consumidor'}",
            conferir=self.repository.conferir_pagamento,
            parent=self,
            empresa=self.empresa,
        )
        if not dialogo.exec():
            return

        try:
            venda = self.repository.finalizar(venda, dialogo.pagamentos)
        except VendaError as erro:
            self._dizer(str(erro), "danger")
            return

        self.itens.clear()
        self.cliente.clear()
        self.desconto.setValue(0.0)
        self._limpar_entrada()
        self._mostrar_foto()
        self.refresh()
        recado = self._lancar_no_financeiro(venda)
        self._anunciar(venda, recado)
        self.data_changed.emit()

    def _lancar_no_financeiro(self, venda) -> str:
        """A prazo vira conta a receber; a vista entra ja recebida."""
        return financeiro.registrar(self.contas, venda)

    def _anunciar(self, venda, extra: str = "") -> None:
        recado = f"Venda {venda.numero} concluída: {fmt.moeda(venda.total)}.{extra}"
        if venda.troco:
            recado += f"  TROCO: {fmt.moeda(venda.troco)}."
        if venda.avisos:
            self._dizer(f"{recado}  Confira o estoque: {'; '.join(venda.avisos)}", "warning")
        else:
            self._dizer(recado, "success")

    def apply_theme(self, palette) -> None:
        self._acao_bipe.setIcon(icons.icon("tag", palette.accent, 16))
        if self.itens:  # o quadro vazio das miniaturas tem a cor do tema
            self._preencher()
