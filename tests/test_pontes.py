"""As pontes entre os modulos.

Duas regras valem para as duas pontes, e sao elas que estes testes protegem:
o modulo de origem continua funcionando sozinho quando o outro nao esta na
licenca, e nada passa duas vezes pela ponte.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.core.contas import AReceber
from dumtech.core.paths import DataPaths
from dumtech.core.pedidos import ItemPedido, Pedido


class PonteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()
        self.abertos: list = []

    def tearDown(self) -> None:
        for aberto in self.abertos:
            aberto.close()

    def contas(self):
        from dumtech.apps.financeiro.contas import abrir_contas

        ponte = abrir_contas(self.paths.app_db("financeiro"))
        self.abertos.append(ponte)
        return ponte

    def destino_vendas(self):
        from dumtech.apps.vendas.pedidos import abrir_destino

        destino = abrir_destino(self.paths.app_db("vendas"))
        self.abertos.append(destino)
        return destino

    def destino_ordens(self):
        from dumtech.apps.ordens.pedidos import abrir_destino

        destino = abrir_destino(self.paths.app_db("ordens"))
        self.abertos.append(destino)
        return destino


class ContasTestCase(PonteTestCase):
    def _conta(self, **campos) -> AReceber:
        dados = dict(descricao="Venda VEN-2026-0001", valor=250.0,
                     vencimento=date.today().isoformat(), cliente="Ana",
                     documento="VEN-2026-0001")
        dados.update(campos)
        return AReceber(**dados)

    def test_lanca_a_conta_a_receber(self) -> None:
        ponte = self.contas()
        conta_id = ponte.lancar(self._conta())

        lancamento = ponte.repository.obter(conta_id)
        self.assertEqual(lancamento.cliente, "Ana")
        self.assertEqual(lancamento.valor, 250.0)
        self.assertFalse(lancamento.pago)

    def test_o_mesmo_documento_nao_vira_duas_contas(self) -> None:
        """A ponte precisa saber o que ela mesma ja lancou."""
        ponte = self.contas()
        self.assertFalse(ponte.ja_lancado("VEN-2026-0001"))

        ponte.lancar(self._conta())
        self.assertTrue(ponte.ja_lancado("VEN-2026-0001"))
        self.assertFalse(ponte.ja_lancado("VEN-2026-0002"))

    def test_documento_vazio_nunca_conta_como_lancado(self) -> None:
        ponte = self.contas()
        ponte.lancar(self._conta(documento=""))
        self.assertFalse(ponte.ja_lancado(""))

    def test_quitar_fecha_a_conta_quando_o_cliente_paga(self) -> None:
        """Sem isso o Financeiro cobraria uma venda que ja foi recebida."""
        ponte = self.contas()
        conta_id = ponte.lancar(self._conta())

        self.assertTrue(ponte.quitar("VEN-2026-0001"))
        self.assertTrue(ponte.repository.obter(conta_id).pago)

        # ja quitada, e documento que nunca existiu: nenhum dos dois e erro
        self.assertFalse(ponte.quitar("VEN-2026-0001"))
        self.assertFalse(ponte.quitar("VEN-2026-9999"))


class VendaNoFinanceiroTestCase(PonteTestCase):
    """Toda venda cai no Financeiro, nao so a prazo."""

    def _venda(self, status: str, numero: str = "VEN-2026-0001"):
        from dumtech.apps.vendas.models import ItemVenda, Pagamento, Venda

        return Venda(numero=numero, cliente="Ana", status=status,
                     itens=[ItemVenda(descricao="Capa", quantidade=2, valor_unitario=50.0)],
                     pagamentos=[Pagamento(forma="Pix", valor=100.0)])

    def _lancamento(self, ponte, numero: str = "VEN-2026-0001"):
        achado = ponte._achar(numero)
        return ponte.repository.obter(int(achado["id"])) if achado else None

    def test_venda_a_vista_entra_ja_recebida(self) -> None:
        from dumtech.apps.vendas import financeiro
        from dumtech.apps.vendas.models import CONCLUIDA

        ponte = self.contas()
        recado = financeiro.registrar(ponte, self._venda(CONCLUIDA))

        lancamento = self._lancamento(ponte)
        self.assertIn("Recebimento", recado)
        self.assertEqual(lancamento.valor, 100.0)
        self.assertTrue(lancamento.pago)
        # registrar de novo nao dobra a receita
        financeiro.registrar(ponte, self._venda(CONCLUIDA))
        self.assertEqual(ponte.repository.obter(lancamento.id).valor, 100.0)
        self.assertEqual(ponte.database.scalar("SELECT COUNT(*) FROM lancamentos"), 1)

    def test_venda_a_prazo_vira_conta_e_fecha_quando_recebe(self) -> None:
        from dumtech.apps.vendas import financeiro
        from dumtech.apps.vendas.models import CONCLUIDA, PENDENTE

        ponte = self.contas()
        financeiro.registrar(ponte, self._venda(PENDENTE))
        self.assertFalse(self._lancamento(ponte).pago)

        financeiro.registrar(ponte, self._venda(CONCLUIDA))
        self.assertTrue(self._lancamento(ponte).pago)
        self.assertEqual(ponte.database.scalar("SELECT COUNT(*) FROM lancamentos"), 1)

    def test_venda_cancelada_ou_sem_financeiro_nao_passa(self) -> None:
        from dumtech.apps.vendas import financeiro
        from dumtech.apps.vendas.models import CANCELADA, CONCLUIDA

        ponte = self.contas()
        self.assertEqual(financeiro.registrar(ponte, self._venda(CANCELADA)), "")
        self.assertIsNone(self._lancamento(ponte))
        self.assertEqual(financeiro.registrar(None, self._venda(CONCLUIDA)), "")


class PedidoTestCase(PonteTestCase):
    def _pedido(self, **campos) -> Pedido:
        dados = dict(
            cliente="Mercado Bom Preco", origem="ORC-2026-0042",
            observacoes="Instalacao inclusa",
            itens=[
                ItemPedido(descricao="Prateleira", quantidade=6,
                           valor_unitario=100.0, unidade="un", desconto=60.0),
                ItemPedido(descricao="Montagem", valor_unitario=850.0),
            ],
        )
        dados.update(campos)
        return Pedido(**dados)

    def test_a_proposta_vira_venda_pendente(self) -> None:
        """Aprovada nao e paga: quem fecha o pagamento e o balcao."""
        from dumtech.apps.vendas.models import PENDENTE

        destino = self.destino_vendas()
        numero = destino.abrir(self._pedido())

        venda = destino.repository.listar()[0]
        self.assertEqual(venda.numero, numero)
        self.assertEqual(venda.status, PENDENTE)
        self.assertEqual(venda.cliente, "Mercado Bom Preco")
        self.assertIn("ORC-2026-0042", venda.observacoes)

    def test_o_desconto_por_item_entra_no_preco(self) -> None:
        """A venda nao tem desconto por linha - e o total tem que bater."""
        destino = self.destino_vendas()
        destino.abrir(self._pedido())

        venda = destino.repository.obter(destino.repository.listar()[0].id)
        prateleira = next(i for i in venda.itens if i.descricao == "Prateleira")
        self.assertEqual(prateleira.valor_unitario, 90.0)  # 600 - 60, em 6 itens
        self.assertEqual(venda.total, 1390.0)

    def test_a_proposta_vira_ordem_ja_aprovada(self) -> None:
        """O cliente aceitou por escrito: a oficina nao pede aprovacao de novo."""
        from dumtech.apps.ordens.models import ANDAMENTO

        destino = self.destino_ordens()
        numero = destino.abrir(self._pedido())

        ordem = destino.repository.obter(destino.repository.listar()[0].id)
        self.assertEqual(ordem.numero, numero)
        self.assertEqual(ordem.status, ANDAMENTO)
        self.assertTrue(ordem.aprovada)
        self.assertTrue(ordem.aprovado_em)
        self.assertEqual(len(ordem.itens), 2)
        self.assertEqual(ordem.total, 1390.0)

    def test_proposta_sem_itens_ainda_abre_uma_ficha_identificavel(self) -> None:
        """Sem itens nao ha item a nomear - mas a ordem nao pode nascer muda.

        O item e opcional em qualquer ramo, entao quem identifica a ordem no
        quadro e nos comprovantes e o que foi pedido, nao um texto inventado.
        """
        destino = self.destino_ordens()
        destino.abrir(self._pedido(itens=[]))

        ordem = destino.repository.listar()[0]
        self.assertEqual(ordem.equipamento, "")
        self.assertTrue(ordem.assunto)

    def test_os_destinos_cumprem_o_contrato(self) -> None:
        from dumtech.core.pedidos import Destino

        for destino in (self.destino_vendas(), self.destino_ordens()):
            with self.subTest(destino.app_id):
                self.assertIsInstance(destino, Destino)
                self.assertTrue(destino.titulo)


class SemLicencaTestCase(unittest.TestCase):
    """A regra que sustenta as duas pontes: sem o outro modulo, nada muda."""

    def setUp(self) -> None:
        from dumtech.core.licensing import LicenseService
        from dumtech.core.registry import AppRegistry
        from dumtech.hub.launcher import AppLauncher

        self.servico = LicenseService()
        self.launcher = AppLauncher(AppRegistry(self.servico), None, None)

    def test_sem_financeiro_a_ponte_de_contas_nao_existe(self) -> None:
        self.launcher.registry.license_service.allows = lambda app_id: False
        self.assertIsNone(self.launcher.contas("vendas"))

    def test_o_financeiro_nao_recebe_a_propria_ponte(self) -> None:
        self.launcher.registry.license_service.allows = lambda app_id: True
        self.assertIsNone(self.launcher.contas("financeiro"))

    def test_so_o_orcamentos_recebe_destinos(self) -> None:
        self.launcher.registry.license_service.allows = lambda app_id: True
        self.assertEqual(self.launcher.destinos("vendas"), [])

    def test_sem_vendas_nem_ordens_a_lista_de_destinos_e_vazia(self) -> None:
        self.launcher.registry.license_service.allows = lambda app_id: False
        self.assertEqual(self.launcher.destinos("orcamentos"), [])


if __name__ == "__main__":
    unittest.main()
