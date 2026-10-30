"""Formulario de cliente."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from ....core import cep as nucleo_cep
from ....core.contacts import UFS, Contato, ContactsStore
from ....core.documentos import formatar_documento, tipo_documento
from ....ui import tasks
from ....ui.widgets import form
from ....ui.widgets.common import label
from ....ui.widgets.form import FormDialog


class ClienteDialog(FormDialog):
    def __init__(
        self,
        store: ContactsStore,
        contato: Contato | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self.store = store
        self.contato = contato or Contato()
        self.editando = contato is not None
        super().__init__(
            "Editar cliente" if self.editando else "Novo cliente",
            "Dados usados por todos os aplicativos DumTech",
            parent,
            largura=640,
        )

        self.nome = form.texto(self.contato.nome, "Ex.: João da Silva")
        self.add_row("Nome", self.nome)

        self.documento = form.texto(self.contato.documento_formatado, "CPF ou CNPJ")
        self.documento.editingFinished.connect(self._documento_mudou)
        self.segmento = form.combo_sugestao(self.contato.segmento, store.segmentos(), "Ex.: Revenda")
        self.add_row("Documento", form.linha(self.documento, "Segmento", self.segmento))
        self.dica_documento = label("", "dim")
        self.form.addRow("", self.dica_documento)

        self.telefone = form.texto(self.contato.telefone_formatado, "(00) 0000-0000")
        self.whatsapp = form.texto(self.contato.whatsapp_formatado, "(00) 00000-0000")
        self.add_row("Telefone", form.linha(self.telefone, "WhatsApp", self.whatsapp))

        self.email = form.texto(self.contato.email, "email@exemplo.com")
        self.nascimento = form.data_opcional(self.contato.nascimento)
        self.add_row("E-mail", form.linha(self.email, "Nascimento", self.nascimento))

        self.cep = form.texto(self.contato.cep_formatado, "00000-000")
        # o endereco chega sozinho assim que o CEP fecha oito digitos
        self.cep.textEdited.connect(self._cep_mudou)
        self.cep.editingFinished.connect(self._buscar_cep)
        self.bairro = form.texto(self.contato.bairro, "Bairro")
        self.add_row("CEP", form.linha(self.cep, "Bairro", self.bairro))
        self.dica_cep = label("", "dim")
        self.form.addRow("", self.dica_cep)

        self.endereco = form.texto(self.contato.endereco, "Rua, avenida...")
        self.numero = form.texto(self.contato.numero, "Número")
        self.add_row("Endereço", form.linha(self.endereco, "Número", self.numero))

        self.complemento = form.texto(self.contato.complemento, "Apto, sala, ponto de referência")
        self.add_row("Complemento", self.complemento)

        self.cidade = form.combo_sugestao(self.contato.cidade, store.cidades(), "Cidade")
        self.uf = form.escolha([("", "")] + [(uf, uf) for uf in UFS], self.contato.uf)
        self.uf.setMaximumWidth(90)
        self.add_row("Cidade", form.linha(self.cidade, "UF", self.uf))

        # quem mandou o cliente: e daqui que sai o "quanto cada parceiro indicou"
        atual = self.contato.parceiro_id
        parceiros = [p for p in store.parceiros(incluir_inativos=True)
                     if p.ativo or p.id == atual]
        self.parceiro = form.escolha(
            [("Ninguém - veio por conta própria", None)]
            + [(p.nome, p.id) for p in parceiros],
            atual,
        )
        self.parceiro.setToolTip("Cadastre os parceiros na tela Parceiros")
        self.add_row("Indicado por", self.parceiro)

        self.observacoes = form.area(self.contato.observacoes, "Anotações gerais sobre o cliente")
        self.add_row("Observações", self.observacoes)

        if self.editando:
            self.ativo = QCheckBox("Cliente ativo (aparece nas listas e nas sugestões)")
            self.ativo.setChecked(self.contato.ativo)
            self.add_row("", self.ativo)

        self.add_note(
            "Digite o CEP e o endereço se preenche sozinho. O CPF/CNPJ é conferido "
            "pelo dígito verificador, e o aniversário (dd/mm/aaaa) alimenta a lista "
            "de aniversariantes do mês no painel."
        )
        self._documento_mudou()
        self.nome.setFocus()

    # ------------------------------------------------------------------ campos
    # --------------------------------------------------------------------- CEP
    def _cep_mudou(self, texto: str) -> None:
        """Formata enquanto digita e busca sozinho quando fecha os 8 digitos."""
        formatado = nucleo_cep.formatar(texto)
        if formatado != texto:
            self.cep.setText(formatado)
            self.cep.setCursorPosition(len(formatado))
        if nucleo_cep.completo(formatado):
            self._buscar_cep()
        else:
            self.dica_cep.setText("")

    def _buscar_cep(self) -> None:
        """Pergunta o endereco em segundo plano - a janela nao pode congelar.

        Preenche rua, bairro, cidade e UF e joga o cursor para o numero, que e
        a unica parte que o CEP nunca sabe. Deu errado (sem internet, CEP que
        nao existe), a tela so avisa e o cadastro segue na mao.
        """
        procurado = self.cep.text()
        if not nucleo_cep.completo(procurado):
            return
        if procurado == getattr(self, "_cep_buscado", ""):
            return                      # ja perguntamos por este
        self._cep_buscado = procurado
        self.dica_cep.setText("Procurando o endereço...")

        tasks.executar(self, lambda: nucleo_cep.buscar(procurado),
                       self._preencher_endereco,
                       lambda _erro: self.dica_cep.setText(""))

    def _preencher_endereco(self, endereco) -> None:
        """Escreve nos campos o que o CEP respondeu (None = nao achou)."""
        if endereco is None:
            self.dica_cep.setText(
                "Não achei este CEP (sem internet ou CEP inexistente) - "
                "pode escrever o endereço na mão."
            )
            return
        if endereco.logradouro:
            self.endereco.setText(endereco.logradouro)
        if endereco.bairro:
            self.bairro.setText(endereco.bairro)
        if endereco.cidade:
            self.cidade.setCurrentText(endereco.cidade)
        if endereco.uf:
            posicao = self.uf.findData(endereco.uf)
            if posicao >= 0:
                self.uf.setCurrentIndex(posicao)
        self.dica_cep.setText(f"{endereco.cidade} - {endereco.uf}".strip(" -"))
        # o numero e a unica parte que o CEP nunca sabe: o cursor ja vai para la
        self.numero.setFocus()
        self.numero.selectAll()

    def _documento_mudou(self) -> None:
        """Formata na hora e diz se e CPF ou CNPJ - erro aparece antes de salvar."""
        texto = self.documento.text().strip()
        if not texto:
            self.dica_documento.setText("")
            return
        tipo = tipo_documento(texto)
        if tipo:
            self.documento.setText(formatar_documento(texto))
            self.dica_documento.setText(f"{tipo} reconhecido")
        else:
            self.dica_documento.setText(
                "Ainda não parece um CPF (11 dígitos) nem um CNPJ (14 dígitos)"
            )

    # ------------------------------------------------------------------ salvar
    def salvar(self) -> None:
        self.contato.nome = self.nome.text()
        self.contato.documento = self.documento.text()
        self.contato.segmento = self.segmento.currentText()
        self.contato.telefone = self.telefone.text()
        self.contato.whatsapp = self.whatsapp.text()
        self.contato.email = self.email.text()
        self.contato.nascimento = self.nascimento.iso()
        self.contato.cep = self.cep.text()
        self.contato.bairro = self.bairro.text()
        self.contato.endereco = self.endereco.text()
        self.contato.numero = self.numero.text()
        self.contato.complemento = self.complemento.text()
        self.contato.cidade = self.cidade.currentText()
        self.contato.uf = self.uf.currentData() or ""
        self.contato.observacoes = self.observacoes.toPlainText()
        self.contato.parceiro_id = self.parceiro.currentData() or None
        if self.editando:
            self.contato.ativo = self.ativo.isChecked()

        if self.editando:
            self.store.atualizar(self.contato)
        else:
            self.store.criar(self.contato)
