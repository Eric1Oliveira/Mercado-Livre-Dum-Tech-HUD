"""O Hub no celular: o resumo que cada modulo manda e a conversa com o servidor.

Como em test_avisos, os modulos sao chamados DIRETO (o `coletar` engole
excecao de proposito e esconderia o erro que interessa).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dumtech.core import celular
from dumtech.core.paths import DataPaths
from dumtech.core.supabase import SemConexao


def dia(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _modulos() -> list:
    from importlib import import_module

    from dumtech.apps import INSTALLED_APPS

    return [m for m in (import_module(c) for c in INSTALLED_APPS) if callable(getattr(m, "celular", None))]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()

    def textos(self, secao: dict) -> str:
        return json.dumps(secao, ensure_ascii=False)


class ContratoTestCase(Base):
    def test_todo_aplicativo_tem_secao_no_celular(self) -> None:
        self.assertEqual(len(_modulos()), 7)

    def test_banco_vazio_nao_quebra_e_vira_json(self) -> None:
        """Primeiro dia de uso: a secao sai, com os textos de "nada ainda"."""
        for modulo in _modulos():
            with self.subTest(modulo.MANIFEST.app_id):
                secao = modulo.celular(self.paths)
                self.assertEqual(secao["app"], modulo.MANIFEST.app_id.upper())
                self.assertTrue(secao["cartoes"])
                json.dumps(secao)  # vai pela rede: tem de virar JSON

    def test_modulo_quebrado_nao_derruba_o_resumo(self) -> None:
        class Quebrado:
            __name__ = "quebrado"

            @staticmethod
            def celular(paths):
                raise RuntimeError("banco corrompido")

        with self.assertLogs("dumtech.core.celular", level="ERROR"):
            self.assertIsNone(celular.coletar(Quebrado(), self.paths))

    def test_dinheiro_vem_primeiro_e_so_entra_o_que_foi_passado(self) -> None:
        por_id = {m.MANIFEST.app_id: m for m in _modulos()}
        entradas = [SimpleNamespace(module=por_id[a]) for a in ("agenda", "vendas", "estoque")]
        resumo = celular.montar(entradas, self.paths, empresa="Padaria", versao="1.2.7")
        self.assertEqual([s["app"] for s in resumo["secoes"]], ["VENDAS", "ESTOQUE", "AGENDA"])
        self.assertEqual(resumo["empresa"], "Padaria")
        self.assertEqual(resumo["formato"], celular.FORMATO)

    def test_lista_corta_no_limite(self) -> None:
        linhas = [celular.linha(str(i)) for i in range(30)]
        self.assertEqual(len(celular.lista("x", linhas)["linhas"]), celular.LIMITE_LISTA)

    def test_codigo_vai_depois_do_hash(self) -> None:
        link = celular.link_de_pareamento("abc")
        self.assertTrue(link.startswith("https://"))
        self.assertTrue(link.endswith("/celular/#p=abc"))

    def test_loja_local_nao_vira_link_de_celular(self) -> None:
        with mock.patch.object(celular, "url_base", return_value="file:///C:/loja"):
            self.assertTrue(celular.link_de_pareamento("x").startswith(celular.URL_PADRAO))


class ConteudoTestCase(Base):
    def test_financeiro_mostra_o_atrasado(self) -> None:
        import dumtech.apps.financeiro.module as modulo
        from dumtech.apps.financeiro.database import open_database
        from dumtech.apps.financeiro.models import RECEITA, Conta, Lancamento
        from dumtech.apps.financeiro.repository import FinanceiroRepository

        banco = open_database(self.paths.app_db("financeiro"))
        repositorio = FinanceiroRepository(banco)
        conta = repositorio.criar_conta(Conta(nome="Banco", saldo_inicial=1000.0))
        repositorio.criar(Lancamento(tipo=RECEITA, descricao="Manutencao", cliente="Joao",
                                     valor=450.0, vencimento=dia(-3), conta_id=conta.id))
        banco.close()

        secao = modulo.celular(self.paths)
        atrasado = next(c for c in secao["cartoes"] if c["rotulo"] == "Atrasado")
        self.assertEqual(atrasado["tom"], "perigo")
        self.assertIn("R$ 450,00", atrasado["valor"])
        self.assertIn("Manutencao", self.textos(secao))

    def test_ordens_mostra_a_pronta_para_entregar(self) -> None:
        import dumtech.apps.ordens.module as modulo
        from dumtech.apps.ordens.database import open_database
        from dumtech.apps.ordens.models import CONCLUIDA, Ordem
        from dumtech.apps.ordens.repository import OrdensRepository

        banco = open_database(self.paths.app_db("ordens"))
        repositorio = OrdensRepository(banco)
        repositorio.salvar(Ordem(numero=repositorio.proximo_numero(), cliente="Bia",
                                 equipamento="Impressora", defeito="Atola", aberta_em=dia(-3),
                                 prazo=dia(3), status=CONCLUIDA, concluida_em=dia(-1)))
        repositorio.salvar(Ordem(numero=repositorio.proximo_numero(), cliente="Ana",
                                 equipamento="Notebook", defeito="Nao liga",
                                 aberta_em=dia(-10), prazo=dia(-2)))
        banco.close()

        secao = modulo.celular(self.paths)
        prontas = next(item for item in secao["listas"] if item["titulo"] == "Prontas para entregar")
        self.assertEqual([linha["texto"] for linha in prontas["linhas"]], ["Bia"])
        atrasadas = next(c for c in secao["cartoes"] if c["rotulo"] == "Atrasadas")
        self.assertEqual((atrasadas["valor"], atrasadas["tom"]), ("1", "perigo"))

    def test_estoque_mostra_o_que_esta_acabando(self) -> None:
        import dumtech.apps.estoque.module as modulo
        from dumtech.apps.estoque.database import open_database
        from dumtech.apps.estoque.models import Produto
        from dumtech.apps.estoque.repository import EstoqueRepository

        banco = open_database(self.paths.app_db("estoque"))
        EstoqueRepository(banco).criar(Produto(codigo="PAR-3", nome="Parafuso 3mm",
                                               estoque_minimo=10, quantidade=2.0))
        banco.close()

        self.assertIn("Parafuso 3mm", self.textos(modulo.celular(self.paths)))

    def test_vendas_mostra_a_venda_do_dia(self) -> None:
        import dumtech.apps.vendas.module as modulo
        from dumtech.apps.vendas.database import open_database
        from dumtech.apps.vendas.models import ItemVenda, Venda
        from dumtech.apps.vendas.repository import VendasRepository

        banco = open_database(self.paths.app_db("vendas"))
        repositorio = VendasRepository(banco)
        repositorio.salvar(Venda(numero=repositorio.proximo_numero(), cliente="Ana",
                                 itens=[ItemVenda(descricao="Produto", quantidade=2, valor_unitario=25.0)]))
        banco.close()

        secao = modulo.celular(self.paths)
        self.assertEqual(secao["cartoes"][0]["valor"], "R$ 50,00")
        self.assertIn("Ana", self.textos(secao))

    def test_agenda_mostra_o_compromisso_de_hoje(self) -> None:
        import dumtech.apps.agenda.module as modulo
        from dumtech.apps.agenda.database import open_database
        from dumtech.apps.agenda.models import Compromisso
        from dumtech.apps.agenda.repository import AgendaRepository

        banco = open_database(self.paths.app_db("agenda"))
        AgendaRepository(banco).salvar(Compromisso(
            titulo="Visita tecnica", cliente="Joao",
            inicio=f"{date.today().isoformat()}T23:30:00", duracao_min=20))
        banco.close()

        self.assertIn("Visita tecnica", self.textos(modulo.celular(self.paths)))

    def test_clientes_mostra_o_aniversariante(self) -> None:
        import dumtech.apps.clientes.module as modulo
        from dumtech.core.contacts import ContactsStore, Contato

        hoje = date.today()
        loja = ContactsStore(self.paths.platform_db)
        loja.criar(Contato(nome="Carlos Menezes", nascimento=hoje.replace(year=hoje.year - 40).isoformat()))
        loja.close()

        self.assertIn("Carlos Menezes", self.textos(modulo.celular(self.paths)))


class ClienteFalso:
    def __init__(self, resposta=None, erro=None) -> None:
        self.resposta, self.erro, self.chamadas = resposta, erro, []

    def rpc(self, funcao, params=None):
        self.chamadas.append((funcao, params))
        if self.erro:
            raise self.erro
        return self.resposta


def _licenca(chave="DT-1", ativa=True):
    return SimpleNamespace(key=chave, machine="MAQ-1", ativa=ativa)


class ServicoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(celular.assinatura, "computador_id", return_value="pc1")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_manda_chave_maquina_e_computador(self) -> None:
        cliente = ClienteFalso({"ok": True, "codigo": "c0d1g0", "expira_em": "x"})
        resposta = celular.CelularService(_licenca, cliente).iniciar()
        funcao, params = cliente.chamadas[0]
        self.assertEqual(funcao, "dumtech_celular_iniciar")
        self.assertEqual(params, {"p_chave": "DT-1", "p_maquina": "MAQ-1", "p_computador": "pc1"})
        self.assertTrue(resposta["link"].endswith("#p=c0d1g0"))

    def test_sem_licenca_nem_pergunta_ao_servidor(self) -> None:
        cliente = ClienteFalso({"ok": True})
        with self.assertRaises(celular.CelularError):
            celular.CelularService(lambda: _licenca(ativa=False), cliente).iniciar()
        self.assertEqual(cliente.chamadas, [])

    def test_erro_do_servidor_vira_frase(self) -> None:
        cliente = ClienteFalso({"ok": False, "erro": "licenca_invalida"})
        with self.assertRaisesRegex(celular.CelularError, "não está ativa neste computador"):
            celular.CelularService(_licenca, cliente).aparelhos()

    def test_sem_internet_vira_frase(self) -> None:
        cliente = ClienteFalso(erro=SemConexao("dns"))
        with self.assertRaisesRegex(celular.CelularError, "Sem internet"):
            celular.CelularService(_licenca, cliente).publicar({"secoes": []})

    def test_publicar_devolve_quantos_celulares(self) -> None:
        cliente = ClienteFalso({"ok": True, "pareados": 2})
        self.assertEqual(celular.CelularService(_licenca, cliente).publicar({"secoes": []}), 2)
        self.assertEqual(cliente.chamadas[0][1]["p_dados"], {"secoes": []})


if __name__ == "__main__":
    unittest.main()
