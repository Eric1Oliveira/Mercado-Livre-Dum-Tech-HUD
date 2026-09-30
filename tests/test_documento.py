"""O documento A4 - a folha que vai por e-mail.

Testar HTML por dentro seria testar a decoracao. O que importa aqui e outra
coisa: que a informacao chegue na folha, que texto do cliente nao vire codigo,
que o PDF saia mesmo do disco e que o papel funcione sem empresa preenchida.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QImage

from dumtech.apps.orcamentos.models import APROVADO, ItemOrcamento, Orcamento
from dumtech.apps.ordens.models import ENTREGUE, ItemOS, Ordem, PECA, SERVICO
from dumtech.core.empresa import Empresa, guardar_logo
from dumtech.core.paths import DataPaths
from dumtech.ui import documento as doc
from dumtech.ui.widgets.documento import nome_de_arquivo

_app = None


def setUpModule() -> None:
    """QTextDocument e QPdfWriter precisam de uma aplicacao Qt viva."""
    global _app
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])


def _empresa(**campos) -> Empresa:
    dados = dict(
        nome="Casa do Parafuso", documento="11222333000181",
        telefone="6332258899", email="contato@casa.com.br",
        endereco="Avenida JK", numero="1200", cidade="Palmas", uf="TO",
    )
    dados.update(campos)
    return Empresa(**dados)


def _orcamento(**campos) -> Orcamento:
    dados = dict(
        numero="ORC-2026-0042", cliente="Mercado Bom Preco",
        condicao_pagamento="50% na entrada", prazo_entrega="10 dias uteis",
        itens=[
            ItemOrcamento(descricao="Prateleira industrial", quantidade=6,
                          valor_unitario=489.9, unidade="un"),
            ItemOrcamento(descricao="Montagem", valor_unitario=850.0),
        ],
    )
    dados.update(campos)
    return Orcamento(**dados)


def _ordem(**campos) -> Ordem:
    dados = dict(
        numero="OS-2026-0117", cliente="Joana Ribeiro", telefone="63988774411",
        equipamento="Notebook Dell", defeito="Nao liga",
        diagnostico="Placa oxidada; conector trocado", tecnico="Marcos",
        status=ENTREGUE, entregue_em="2026-08-28", garantia_dias=90,
        itens=[
            ItemOS(tipo=PECA, descricao="Conector DC", valor_unitario=95.0),
            ItemOS(tipo=SERVICO, descricao="Reparo de placa", valor_unitario=280.0),
        ],
    )
    dados.update(campos)
    return Ordem(**dados)


class PedacosTestCase(unittest.TestCase):
    """As pecas do motor, sem nenhum aplicativo envolvido."""

    def test_pedaco_vazio_nao_entra_na_folha(self) -> None:
        """O consumidor manda tudo; quem nao tem conteudo some sozinho."""
        self.assertEqual(doc.tabela(["A"], []), "")
        self.assertEqual(doc.secao("Observacoes", "   "), "")
        self.assertEqual(doc.campos([("Cliente", "")]), "")
        self.assertEqual(doc.rodape(Empresa()), "")

    def test_sem_empresa_a_folha_sai_sem_cabecalho(self) -> None:
        """Mesma regra da bobina: util no primeiro dia, sem configurar nada."""
        self.assertEqual(doc.cabecalho(None), "")
        self.assertEqual(doc.cabecalho(Empresa()), "")

    def test_o_cabecalho_leva_a_identidade_da_empresa(self) -> None:
        html = doc.cabecalho(_empresa())
        self.assertIn("Casa do Parafuso", html)
        self.assertIn("CNPJ: 11.222.333/0001-81", html)
        self.assertIn("Palmas/TO", html)

    def test_texto_do_cliente_nao_vira_codigo(self) -> None:
        """Um nome com < ou & tem que sair como escreveram, nao como marcacao."""
        html = doc.secao("Observacoes", "Desconto <10% & frete a combinar")
        self.assertIn("&lt;10% &amp; frete", html)
        self.assertNotIn("<10%", html)

    def test_quebra_de_linha_digitada_e_preservada(self) -> None:
        self.assertIn("<br>", doc.secao("Observacoes", "primeira\nsegunda"))

    def test_a_regua_tem_conteudo_para_nao_sumir(self) -> None:
        """Celula vazia colada em outra tabela vira altura zero e a borda some."""
        self.assertIn("&nbsp;", doc.regua())

    def test_tabela_aceita_menos_alinhamentos_que_colunas(self) -> None:
        html = doc.tabela(["A", "B"], [["1", "2"]], alinhamentos=[doc.DIREITA])
        self.assertIn('align="right"', html)
        self.assertIn('align="left"', html)


class PropostaTestCase(unittest.TestCase):
    def test_a_folha_leva_itens_condicoes_e_total(self) -> None:
        html = _proposta()
        for esperado in ("Prateleira industrial", "R$ 2.939,40",
                         "50% na entrada", "10 dias uteis", "R$ 3.789,40"):
            self.assertIn(esperado, html)

    def test_proposta_aprovada_ganha_a_faixa(self) -> None:
        self.assertIn("APROVADA", _proposta(status=APROVADO))
        self.assertNotIn("APROVADA", _proposta())

    def test_a_proposta_funciona_sem_empresa(self) -> None:
        html = _proposta(empresa=None)
        self.assertIn("Proposta comercial", html)
        self.assertNotIn("Casa do Parafuso", html)

    def test_validade_em_dias_quando_nao_ha_data(self) -> None:
        self.assertIn("15 dias apos o envio", _proposta(validade_dias=15))


class EntregaTestCase(unittest.TestCase):
    def test_a_folha_leva_servico_garantia_e_assinatura(self) -> None:
        html = _entrega()
        self.assertIn("Placa oxidada", html)
        self.assertIn("GARANTIA DE 90 DIAS", html.upper())
        self.assertIn("Recebi o servico", html)

    def test_telefone_sai_formatado(self) -> None:
        """O banco guarda so digitos; o papel do cliente nao pode mostrar isso."""
        self.assertIn("(63) 98877-4411", _entrega())

    def test_sem_garantia_o_papel_diz_isso_em_vez_de_omitir(self) -> None:
        html = _entrega(garantia_dias=0)
        self.assertIn("sem garantia", html)

    def test_ordem_cancelada_ganha_a_faixa(self) -> None:
        from dumtech.apps.ordens.models import CANCELADA

        self.assertIn("CANCELADA", _entrega(status=CANCELADA))


class PdfTestCase(unittest.TestCase):
    """O PDF e o produto desta frente: tem que existir mesmo, em disco."""

    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp())

    def test_grava_um_pdf_de_verdade(self) -> None:
        destino = doc.salvar_pdf(_proposta(), self.pasta / "proposta.pdf",
                                 _empresa())
        self.assertTrue(destino.exists())
        self.assertTrue(destino.read_bytes().startswith(b"%PDF"))
        self.assertGreater(destino.stat().st_size, 1000)

    def test_cria_a_pasta_que_faltar(self) -> None:
        destino = doc.salvar_pdf(_entrega(), self.pasta / "nova" / "os.pdf")
        self.assertTrue(destino.exists())

    def test_nome_de_arquivo_aceita_o_que_o_windows_aceita(self) -> None:
        self.assertEqual(
            nome_de_arquivo("Proposta ORC-1/2026: Joao?"),
            "Proposta ORC-1 2026 Joao"
        )
        self.assertEqual(nome_de_arquivo(""), "documento")
        self.assertEqual(nome_de_arquivo("///"), "documento")


class LogoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()

    def _com_logo(self) -> Empresa:
        arquivo = self.paths.root / "marca.png"
        QImage(120, 60, QImage.Format.Format_RGB32).save(str(arquivo))
        return _empresa(logo=guardar_logo(arquivo, self.paths))

    def test_o_logotipo_entra_como_recurso_do_documento(self) -> None:
        """Por recurso, e nao por `file://`: ha acento no caminho do programa."""
        empresa = self._com_logo()
        self.assertTrue(doc.tem_logo(empresa, self.paths))

        html = doc.cabecalho(empresa, com_logo=True)
        self.assertIn(doc.LOGO, html)

        documento = doc.render(html, empresa, self.paths)
        recurso = documento.resource(
            documento.ResourceType.ImageResource.value, _url(doc.LOGO)
        )
        self.assertFalse(QImage(recurso).isNull())

    def test_arquivo_quebrado_nao_derruba_o_documento(self) -> None:
        (self.paths.config_dir / "logotipo.png").write_bytes(b"nao e imagem")
        empresa = _empresa(logo="logotipo.png")
        self.assertFalse(doc.tem_logo(empresa, self.paths))
        self.assertNotIn(doc.LOGO, doc.cabecalho(empresa, doc.tem_logo(empresa, self.paths)))

    def test_sem_logotipo_o_cabecalho_continua_de_pe(self) -> None:
        self.assertFalse(doc.tem_logo(_empresa(), self.paths))
        self.assertIn("Casa do Parafuso", doc.cabecalho(_empresa()))


def _url(texto: str):
    from PySide6.QtCore import QUrl

    return QUrl(texto)


def _proposta(empresa=_empresa(), **campos) -> str:
    from dumtech.apps.orcamentos.documento import proposta_a4

    return proposta_a4(_orcamento(**campos), empresa)


def _entrega(empresa=_empresa(), **campos) -> str:
    from dumtech.apps.ordens.documento import entrega_a4

    return entrega_a4(_ordem(**campos), empresa)


if __name__ == "__main__":
    unittest.main()
