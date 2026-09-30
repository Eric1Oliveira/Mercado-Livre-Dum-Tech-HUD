"""Regras da ficha do cliente: documento, endereco, anotacoes e aniversario."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from dumtech.core.contacts import Contato, ContactsStore, ContatoError
from dumtech.core.documentos import (
    cnpj_valido,
    cpf_valido,
    documento_valido,
    formatar_documento,
    formatar_telefone,
    tipo_documento,
)

# documentos validos de teste (digito verificador correto)
CPF = "529.982.247-25"
CNPJ = "11.222.333/0001-81"


class DocumentosTestCase(unittest.TestCase):
    def test_cpf_valido_e_invalido(self) -> None:
        self.assertTrue(cpf_valido(CPF))
        self.assertTrue(cpf_valido("52998224725"))
        self.assertFalse(cpf_valido("529.982.247-26"))  # digito errado
        self.assertFalse(cpf_valido("111.111.111-11"))  # passa na conta, nao existe
        self.assertFalse(cpf_valido("123"))

    def test_cnpj_valido_e_invalido(self) -> None:
        self.assertTrue(cnpj_valido(CNPJ))
        self.assertFalse(cnpj_valido("11.222.333/0001-82"))
        self.assertFalse(cnpj_valido("00.000.000/0000-00"))

    def test_documento_vazio_e_aceito(self) -> None:
        """Documento nao e obrigatorio: venda no balcao nem sempre pede."""
        self.assertTrue(documento_valido(""))
        self.assertTrue(documento_valido(None))
        self.assertFalse(documento_valido("123456"))

    def test_tipo_e_formatacao(self) -> None:
        self.assertEqual(tipo_documento(CPF), "CPF")
        self.assertEqual(tipo_documento(CNPJ), "CNPJ")
        self.assertEqual(formatar_documento("52998224725"), "529.982.247-25")
        self.assertEqual(formatar_documento("11222333000181"), "11.222.333/0001-81")
        self.assertEqual(formatar_telefone("63999990000"), "(63) 99999-0000")
        self.assertEqual(formatar_telefone("6332258899"), "(63) 3225-8899")


class FichaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = ContactsStore(Path(tempfile.mkdtemp()) / "plataforma.db")

    def tearDown(self) -> None:
        self.store.close()

    def _cliente(self, nome="Joao da Silva", **campos) -> Contato:
        return self.store.criar(Contato(nome=nome, **campos))

    # ------------------------------------------------------------- documento
    def test_documento_invalido_e_recusado(self) -> None:
        with self.assertRaises(ContatoError):
            self._cliente(documento="529.982.247-26")

    def test_documento_e_guardado_limpo_e_exibido_formatado(self) -> None:
        cliente = self._cliente(documento=CPF)
        salvo = self.store.obter(cliente.id)
        self.assertEqual(salvo.documento, "52998224725")
        self.assertEqual(salvo.documento_formatado, "529.982.247-25")
        self.assertEqual(salvo.tipo_documento, "CPF")

    def test_documento_repetido_e_recusado(self) -> None:
        self._cliente(nome="Primeiro", documento=CPF)
        with self.assertRaises(ContatoError) as erro:
            self._cliente(nome="Segundo", documento="52998224725")
        self.assertIn("Primeiro", str(erro.exception))

    def test_editar_o_proprio_cliente_nao_acusa_duplicidade(self) -> None:
        cliente = self._cliente(documento=CPF)
        cliente.cidade = "Palmas"
        self.store.atualizar(cliente)  # nao levanta
        self.assertEqual(self.store.obter(cliente.id).cidade, "Palmas")

    def test_acha_por_documento_digitado_de_qualquer_jeito(self) -> None:
        cliente = self._cliente(documento=CPF)
        self.assertEqual(self.store.por_documento("529.982.247-25").id, cliente.id)
        self.assertEqual(self.store.por_documento("52998224725").id, cliente.id)
        self.assertIsNone(self.store.por_documento(""))

    # -------------------------------------------------------------- endereco
    def test_endereco_completo_pula_o_que_esta_vazio(self) -> None:
        cliente = self._cliente(
            endereco="Rua das Flores", numero="120", bairro="Centro",
            cidade="Palmas", uf="TO", cep="77000000",
        )
        completo = cliente.endereco_completo
        self.assertIn("Rua das Flores, 120", completo)
        self.assertIn("Palmas/TO", completo)
        self.assertIn("77000-000", completo)

        magro = self._cliente(nome="Sem endereco", cidade="Gurupi")
        self.assertEqual(magro.endereco_completo, "Gurupi")

    def test_uf_inexistente_e_recusada(self) -> None:
        with self.assertRaises(ContatoError):
            self._cliente(uf="XX")

    def test_uf_e_guardada_em_maiusculas(self) -> None:
        cliente = self._cliente(uf="to")
        self.assertEqual(self.store.obter(cliente.id).uf, "TO")

    # ----------------------------------------------------------- aniversario
    def test_aniversariantes_do_mes(self) -> None:
        self._cliente(nome="Faz em marco", nascimento="1990-03-15")
        self._cliente(nome="Faz em marco tambem", nascimento="1985-03-02")
        self._cliente(nome="Faz em julho", nascimento="1992-07-20")

        nomes = [c.nome for c in self.store.aniversariantes(3)]
        # ordenados pelo dia: dia 2 antes do dia 15
        self.assertEqual(nomes, ["Faz em marco tambem", "Faz em marco"])
        self.assertEqual(len(self.store.aniversariantes(7)), 1)
        self.assertEqual(self.store.aniversariantes(1), [])

    def test_idade_calculada(self) -> None:
        nascimento = date.today().replace(year=date.today().year - 30)
        cliente = self._cliente(nascimento=nascimento.isoformat())
        self.assertEqual(cliente.idade, 30)
        self.assertIsNone(self._cliente(nome="Sem data").idade)

    def test_idade_no_ano_vale_antes_e_depois_do_aniversario(self) -> None:
        """O numero da lista de aniversariantes nao pode depender do dia de hoje."""
        ano = date.today().year - 40
        janeiro = self._cliente(nome="Ja fez", nascimento=f"{ano}-01-10")
        dezembro = self._cliente(nome="Ainda vai fazer", nascimento=f"{ano}-12-20")
        self.assertEqual(janeiro.idade_neste_ano, 40)
        self.assertEqual(dezembro.idade_neste_ano, 40)

    def test_nascimento_no_futuro_e_recusado(self) -> None:
        futuro = date.today().replace(year=date.today().year + 1)
        with self.assertRaises(ContatoError):
            self._cliente(nascimento=futuro.isoformat())

    # -------------------------------------------------------------- anotacoes
    def test_anotacoes_ficam_em_ordem_com_a_mais_nova_em_cima(self) -> None:
        cliente = self._cliente()
        self.store.anotar(cliente.id, "Ligou pedindo orcamento")
        self.store.anotar(cliente.id, "Passou na loja e fechou")

        notas = self.store.notas(cliente.id)
        self.assertEqual(len(notas), 2)
        self.assertEqual(notas[0].texto, "Passou na loja e fechou")

    def test_anotacao_vazia_e_recusada(self) -> None:
        cliente = self._cliente()
        with self.assertRaises(ContatoError):
            self.store.anotar(cliente.id, "   ")

    def test_excluir_cliente_leva_as_anotacoes_junto(self) -> None:
        cliente = self._cliente()
        self.store.anotar(cliente.id, "Uma anotacao")
        self.store.excluir(cliente.id)
        self.assertEqual(self.store.notas(cliente.id), [])

    # ------------------------------------------------------------ ativo/inativo
    def test_inativar_some_das_listas_e_das_sugestoes(self) -> None:
        cliente = self._cliente()
        self.store.inativar(cliente.id)
        self.assertEqual(self.store.listar(), [])
        self.assertEqual(self.store.nomes(), [])
        self.assertEqual(len(self.store.listar(incluir_inativos=True)), 1)

        self.store.reativar(cliente.id)
        self.assertEqual(len(self.store.listar()), 1)

    # ---------------------------------------------------------------- filtros
    def test_filtra_por_cidade_e_segmento(self) -> None:
        self._cliente(nome="Loja A", cidade="Palmas", segmento="Revenda")
        self._cliente(nome="Loja B", cidade="Palmas", segmento="Consumidor")
        self._cliente(nome="Loja C", cidade="Gurupi", segmento="Revenda")

        self.assertEqual(len(self.store.listar(cidade="Palmas")), 2)
        self.assertEqual(len(self.store.listar(segmento="Revenda")), 2)
        self.assertEqual(len(self.store.listar(cidade="Palmas", segmento="Revenda")), 1)
        self.assertEqual(self.store.cidades(), ["Gurupi", "Palmas"])
        self.assertEqual(self.store.segmentos(), ["Consumidor", "Revenda"])

    def test_busca_alcanca_bairro_e_whatsapp(self) -> None:
        self._cliente(bairro="Plano Diretor Sul", whatsapp="63988887777")
        self.assertEqual(len(self.store.listar("Plano Diretor")), 1)
        self.assertEqual(len(self.store.listar("98888")), 1)

    # ----------------------------------------------------------------- painel
    def test_resumo_do_painel(self) -> None:
        self._cliente(nome="Ativo 1", cidade="Palmas", nascimento="1990-01-05")
        self._cliente(nome="Ativo 2", cidade="Palmas")
        inativo = self._cliente(nome="Inativo", cidade="Gurupi")
        self.store.inativar(inativo.id)

        resumo = self.store.resumo()
        self.assertEqual(resumo.total, 3)
        self.assertEqual(resumo.ativos, 2)
        self.assertEqual(resumo.novos_mes, 3)
        self.assertEqual(resumo.cidades, 1)  # so Palmas continua ativa
        self.assertEqual(resumo.por_cidade, [("Palmas", 2)])
        self.assertEqual(len(resumo.recentes), 2)


class MigracaoTestCase(unittest.TestCase):
    """Quem ja tinha clientes na versao 1 nao pode perder nada."""

    def test_v1_vira_v2_mantendo_os_clientes(self) -> None:
        import sqlite3

        from dumtech.core.contacts import MIGRATIONS

        arquivo = Path(tempfile.mkdtemp()) / "plataforma.db"
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO contatos (id, nome, documento, telefone, email, endereco,"
            " cidade, observacoes, criado_em, atualizado_em)"
            " VALUES (1, 'Maria Souza', '52998224725', '6399999000', 'm@x.com',"
            " 'Rua A', 'Palmas', 'Cliente antiga', '2026-01-05T10:00:00',"
            " '2026-01-05T10:00:00')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        store = ContactsStore(arquivo)
        self.addCleanup(store.close)
        self.assertEqual(store.db.schema_version, 2)

        cliente = store.obter(1)
        self.assertEqual(cliente.nome, "Maria Souza")
        self.assertEqual(cliente.cidade, "Palmas")
        self.assertEqual(cliente.observacoes, "Cliente antiga")
        self.assertEqual(cliente.criado_em, "2026-01-05T10:00:00")
        # campos novos chegam com padrao util
        self.assertTrue(cliente.ativo)
        self.assertEqual(cliente.uf, "")
        self.assertEqual(store.notas(1), [])

        # e o banco migrado continua funcionando
        store.anotar(1, "Voltou a comprar")
        self.assertEqual(len(store.notas(1)), 1)


if __name__ == "__main__":
    unittest.main()
