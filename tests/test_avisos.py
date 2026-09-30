"""A tela "Hoje".

Estes testes chamam `module.avisos()` **direto**, e nao pelo `coletar`: o
`coletar` engole excecao de proposito (modulo quebrado nao pode derrubar o
Inicio do cliente) e por isso esconderia justamente o erro que interessa aqui.
Ja aconteceu uma vez, com um atributo que nao existia.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dumtech.core.avisos import TIPOS, Aviso, Config, coletar, ordenar
from dumtech.core.paths import DataPaths


def dia(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


class BaseAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()
        self.config = Config()

    def avisos_de(self, modulo) -> list[Aviso]:
        return modulo.avisos(self.paths, self.config)

    def tipos(self, avisos) -> list[str]:
        return [a.tipo for a in avisos]


class ContratoTestCase(BaseAppTestCase):
    def test_todo_tipo_pertence_a_um_aplicativo_existente(self) -> None:
        from dumtech.apps import INSTALLED_APPS

        instalados = {caminho.rsplit(".", 2)[-2] for caminho in INSTALLED_APPS}
        for tipo in TIPOS:
            with self.subTest(tipo.chave):
                self.assertIn(tipo.app_id, instalados)

    def test_banco_vazio_nao_avisa_nada_e_nao_quebra(self) -> None:
        """Primeiro dia de uso: nenhum aviso, nenhum erro."""
        for modulo in _modulos_com_avisos():
            with self.subTest(modulo.MANIFEST.app_id):
                self.assertEqual(modulo.avisos(self.paths, self.config), [])

    def test_modulo_sem_avisos_simplesmente_nao_entra(self) -> None:
        class Mudo:
            pass

        self.assertEqual(coletar(Mudo(), self.paths, self.config), [])

    def test_modulo_quebrado_nao_derruba_a_tela(self) -> None:
        class Quebrado:
            __name__ = "quebrado"

            @staticmethod
            def avisos(paths, config):
                raise RuntimeError("banco corrompido")

        with self.assertLogs("dumtech.core.avisos", level="ERROR"):
            self.assertEqual(coletar(Quebrado(), self.paths, self.config), [])

    def test_o_cliente_pode_desligar_um_tipo(self) -> None:
        class Um:
            @staticmethod
            def avisos(paths, config):
                return [Aviso("estoque", "estoque_baixo", "2 produtos")]

        self.assertEqual(len(coletar(Um(), self.paths, self.config)), 1)
        self.config.definir("estoque_baixo", ligado=False)
        self.assertEqual(coletar(Um(), self.paths, self.config), [])

    def test_o_mais_urgente_fica_em_cima(self) -> None:
        avisos = [
            Aviso("agenda", "compromisso_hoje", "hoje", urgencia=40),
            Aviso("financeiro", "conta_vencida", "vencida", urgencia=90),
            Aviso("estoque", "estoque_baixo", "baixo", urgencia=50),
        ]
        self.assertEqual(
            self.tipos(ordenar(avisos)),
            ["conta_vencida", "estoque_baixo", "compromisso_hoje"],
        )


class FinanceiroTestCase(BaseAppTestCase):
    def _semear(self) -> None:
        from dumtech.apps.financeiro.database import open_database
        from dumtech.apps.financeiro.models import DESPESA, RECEITA, Conta, Lancamento
        from dumtech.apps.financeiro.repository import FinanceiroRepository

        banco = open_database(self.paths.app_db("financeiro"))
        repositorio = FinanceiroRepository(banco)
        conta = repositorio.criar_conta(Conta(nome="Banco", saldo_inicial=1000.0))
        repositorio.criar(Lancamento(tipo=RECEITA, descricao="Manutencao",
                                     cliente="Joao", valor=450.0,
                                     vencimento=dia(-3), conta_id=conta.id))
        repositorio.criar(Lancamento(tipo=DESPESA, descricao="Fornecedor",
                                     valor=1340.0, vencimento=dia(3),
                                     conta_id=conta.id))
        banco.close()

    def test_avisa_o_vencido_e_o_que_esta_por_vencer(self) -> None:
        import dumtech.apps.financeiro.module as modulo

        self._semear()
        avisos = self.avisos_de(modulo)
        self.assertEqual(set(self.tipos(avisos)),
                         {"conta_vencida", "conta_vencendo"})

        vencida = next(a for a in avisos if a.tipo == "conta_vencida")
        self.assertEqual(vencida.tom, "danger")
        self.assertIn("R$ 450,00", vencida.detalhe)

    def test_o_prazo_e_do_cliente(self) -> None:
        """Com um dia de antecedencia, a conta de daqui a tres dias nao entra."""
        import dumtech.apps.financeiro.module as modulo

        self._semear()
        self.config.definir("conta_vencendo", dias=1)
        self.assertNotIn("conta_vencendo", self.tipos(self.avisos_de(modulo)))


class OrdensTestCase(BaseAppTestCase):
    def test_avisa_atraso_e_servico_parado_na_prateleira(self) -> None:
        import dumtech.apps.ordens.module as modulo
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.models import CONCLUIDA, Ordem
        from dumtech.apps.ordens.repository import OrdensRepository

        banco = open_database(self.paths.app_db("ordens"))
        repositorio = OrdensRepository(banco)
        repositorio.salvar(Ordem(numero=repositorio.proximo_numero(),
                                 cliente="Ana", equipamento="Notebook",
                                 defeito="Nao liga", aberta_em=dia(-10),
                                 prazo=dia(-2)))
        pronta = repositorio.salvar(Ordem(numero=repositorio.proximo_numero(),
                                          cliente="Bia", equipamento="Impressora",
                                          defeito="Atola papel", aberta_em=dia(-9),
                                          prazo=dia(3), status=CONCLUIDA,
                                          concluida_em=dia(-5)))
        self.assertIsNotNone(pronta.id)
        banco.close()

        self.assertEqual(set(self.tipos(self.avisos_de(modulo))),
                         {"os_atrasada", "os_para_retirar"})

    def test_pronta_hoje_ainda_nao_e_servico_esquecido(self) -> None:
        import dumtech.apps.ordens.module as modulo
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.models import CONCLUIDA, Ordem
        from dumtech.apps.ordens.repository import OrdensRepository

        banco = open_database(self.paths.app_db("ordens"))
        repositorio = OrdensRepository(banco)
        repositorio.salvar(Ordem(numero=repositorio.proximo_numero(),
                                 cliente="Bia", equipamento="Impressora",
                                 defeito="Atola", aberta_em=dia(-2),
                                 prazo=dia(3), status=CONCLUIDA,
                                 concluida_em=dia(0)))
        banco.close()

        self.assertNotIn("os_para_retirar", self.tipos(self.avisos_de(modulo)))


class OrcamentosTestCase(BaseAppTestCase):
    def test_avisa_a_proposta_parada(self) -> None:
        import dumtech.apps.orcamentos.module as modulo
        from dumtech.apps.orcamentos.database import open_database
        from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento
        from dumtech.apps.orcamentos.repository import OrcamentosRepository

        banco = open_database(self.paths.app_db("orcamentos"))
        repositorio = OrcamentosRepository(banco)
        proposta = repositorio.salvar(Orcamento(
            numero=repositorio.proximo_numero(), cliente="Mercado",
            data=dia(-20), validade_dias=30,
            itens=[ItemOrcamento(descricao="Servico", valor_unitario=1000.0)],
        ))
        repositorio.enviar(proposta.id, dia(-20))
        banco.close()

        self.assertIn("proposta_parada", self.tipos(self.avisos_de(modulo)))


class EstoqueTestCase(BaseAppTestCase):
    def test_avisa_o_produto_no_minimo(self) -> None:
        import dumtech.apps.estoque.module as modulo
        from dumtech.apps.estoque.database import open_database
        from dumtech.apps.estoque.models import Produto
        from dumtech.apps.estoque.repository import EstoqueRepository

        banco = open_database(self.paths.app_db("estoque"))
        repositorio = EstoqueRepository(banco)
        repositorio.criar(Produto(codigo="PAR-3", nome="Parafuso 3mm", estoque_minimo=10,
                                  quantidade=2.0))
        banco.close()

        avisos = self.avisos_de(modulo)
        self.assertEqual(self.tipos(avisos), ["estoque_baixo"])
        self.assertIn("Parafuso 3mm", avisos[0].detalhe)


class VendasTestCase(BaseAppTestCase):
    def test_avisa_a_venda_nao_paga(self) -> None:
        import dumtech.apps.vendas.module as modulo
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.models import ItemVenda, PENDENTE, Venda
        from dumtech.apps.vendas.repository import VendasRepository

        banco = open_database(self.paths.app_db("vendas"))
        repositorio = VendasRepository(banco)
        repositorio.salvar(Venda(
            numero=repositorio.proximo_numero(), cliente="Ana", status=PENDENTE,
            itens=[ItemVenda(descricao="Produto", quantidade=2,
                             valor_unitario=25.0)],
        ))
        banco.close()

        avisos = self.avisos_de(modulo)
        self.assertEqual(self.tipos(avisos), ["venda_a_receber"])
        self.assertIn("R$ 50,00", avisos[0].detalhe)


class AgendaTestCase(BaseAppTestCase):
    def test_avisa_o_compromisso_de_hoje(self) -> None:
        import dumtech.apps.agenda.module as modulo
        from dumtech.apps.agenda.database import open_database
        from dumtech.apps.agenda.models import Compromisso
        from dumtech.apps.agenda.repository import AgendaRepository

        banco = open_database(self.paths.app_db("agenda"))
        AgendaRepository(banco).salvar(Compromisso(
            titulo="Visita tecnica", cliente="Joao",
            inicio=f"{date.today().isoformat()}T14:30:00", duracao_min=60,
        ))
        banco.close()

        avisos = self.avisos_de(modulo)
        self.assertEqual(self.tipos(avisos), ["compromisso_hoje"])
        self.assertIn("Visita tecnica", avisos[0].detalhe)


class ClientesTestCase(BaseAppTestCase):
    def test_avisa_o_aniversariante_do_dia(self) -> None:
        import dumtech.apps.clientes.module as modulo
        from dumtech.core.contacts import ContactsStore, Contato

        hoje = date.today()
        loja = ContactsStore(self.paths.platform_db)
        loja.criar(Contato(nome="Carlos Menezes",
                           nascimento=hoje.replace(year=hoje.year - 40).isoformat()))
        loja.criar(Contato(nome="Sem festa hoje",
                           nascimento=(hoje - timedelta(days=40)).isoformat()))
        loja.close()

        avisos = self.avisos_de(modulo)
        self.assertEqual(self.tipos(avisos), ["aniversario_hoje"])
        self.assertIn("Carlos Menezes", avisos[0].titulo)


def _modulos_com_avisos() -> list:
    from dumtech.apps import INSTALLED_APPS
    from importlib import import_module

    modulos = []
    for caminho in INSTALLED_APPS:
        try:
            modulo = import_module(caminho)
        except ImportError:
            continue
        if callable(getattr(modulo, "avisos", None)):
            modulos.append(modulo)
    return modulos


if __name__ == "__main__":
    unittest.main()
