"""Regras da proposta: desconto por item, etapas, funil, duplicar e documento."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dumtech.apps.orcamentos.database import MIGRATIONS, open_database
from dumtech.apps.orcamentos.models import (
    APROVADO,
    ENVIADO,
    MOTIVO_CONCORRENTE,
    MOTIVO_PRECO,
    RASCUNHO,
    RECUSADO,
    ItemOrcamento,
    Orcamento,
    OrcamentoError,
)
from dumtech.apps.orcamentos.recibo import proposta
from dumtech.apps.orcamentos.repository import OrcamentosRepository


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


def dia(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


class OrcamentosBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(_arquivo("orcamentos.db"))
        self.repo = OrcamentosRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _orcamento(self, **campos) -> Orcamento:
        dados = dict(
            numero=self.repo.proximo_numero(),
            cliente="Mercado Central",
            itens=[ItemOrcamento(descricao="Instalacao de rede", valor_unitario=1800.0)],
        )
        dados.update(campos)
        return self.repo.salvar(Orcamento(**dados))


class ValoresTestCase(OrcamentosBase):
    def test_desconto_por_item_e_desconto_na_proposta(self) -> None:
        orcamento = self._orcamento(
            desconto=100.0,
            itens=[
                ItemOrcamento(descricao="Cabo cat6", quantidade=60, valor_unitario=4.5,
                              desconto=20.0, unidade="m"),
                ItemOrcamento(descricao="Instalacao", valor_unitario=1800.0,
                              desconto=180.0),
            ],
        )
        self.assertEqual(orcamento.bruto, 2070.0)
        self.assertEqual(orcamento.descontos_dos_itens, 200.0)
        self.assertEqual(orcamento.subtotal, 1870.0)
        self.assertEqual(orcamento.total, 1770.0)
        self.assertEqual(orcamento.desconto_total, 300.0)

    def test_o_total_fica_gravado_para_a_lista_e_o_funil(self) -> None:
        orcamento = self._orcamento(desconto=300.0)
        self.assertEqual(self.repo.obter(orcamento.id).total_gravado, 1500.0)

    def test_quantidade_fracionada(self) -> None:
        orcamento = self._orcamento(itens=[
            ItemOrcamento(descricao="Granito", quantidade=4.5, valor_unitario=380.0,
                          unidade="m2")
        ])
        self.assertEqual(orcamento.total, 1710.0)
        self.assertEqual(self.repo.obter(orcamento.id).itens[0].quantidade_texto,
                         "4,5 m2")

    def test_desconto_de_item_maior_que_a_linha_e_recusado(self) -> None:
        with self.assertRaises(OrcamentoError):
            self._orcamento(itens=[
                ItemOrcamento(descricao="Servico", valor_unitario=100.0, desconto=500.0)
            ])

    def test_desconto_geral_maior_que_o_subtotal_e_recusado(self) -> None:
        with self.assertRaises(OrcamentoError):
            self._orcamento(desconto=99999.0)

    def test_proposta_sem_item_e_recusada(self) -> None:
        with self.assertRaises(OrcamentoError):
            self._orcamento(itens=[])


class EtapasTestCase(OrcamentosBase):
    def test_enviar_marca_a_data_e_liga_a_validade(self) -> None:
        orcamento = self._orcamento(validade_dias=15)
        self.assertEqual(orcamento.vale_ate, "")   # ainda nao saiu da loja

        enviado = self.repo.enviar(orcamento.id)
        self.assertEqual(enviado.status, ENVIADO)
        self.assertEqual(enviado.enviado_em, dia(0))
        self.assertEqual(enviado.vale_ate, dia(15))
        self.assertFalse(enviado.vencido)
        self.assertEqual(enviado.dias_esperando, 0)

    def test_proposta_vencida_avisa_sem_mudar_de_etapa(self) -> None:
        orcamento = self._orcamento(validade_dias=10)
        self.repo.enviar(orcamento.id, quando=dia(-30))

        salvo = self.repo.obter(orcamento.id)
        self.assertTrue(salvo.vencido)
        self.assertEqual(salvo.status, ENVIADO)   # quem responde e o cliente
        self.assertEqual(salvo.dias_esperando, 30)

    def test_aprovar_guarda_a_resposta(self) -> None:
        orcamento = self._orcamento()
        aprovado = self.repo.aprovar(orcamento.id)
        self.assertEqual(aprovado.status, APROVADO)
        self.assertEqual(aprovado.respondido_em, dia(0))
        self.assertTrue(aprovado.respondido)
        self.assertFalse(aprovado.vencido)

    def test_recusar_exige_motivo_da_lista(self) -> None:
        orcamento = self._orcamento()
        with self.assertRaises(OrcamentoError):
            self.repo.recusar(orcamento.id, "porque sim")
        with self.assertRaises(OrcamentoError):
            self.repo.recusar(orcamento.id, "")

        recusado = self.repo.recusar(orcamento.id, MOTIVO_PRECO)
        self.assertEqual(recusado.status, RECUSADO)
        self.assertEqual(recusado.motivo_label, "Achou caro")
        self.assertEqual(recusado.respondido_em, dia(0))

    def test_reabrir_limpa_a_resposta(self) -> None:
        orcamento = self._orcamento()
        self.repo.enviar(orcamento.id)
        self.repo.recusar(orcamento.id, MOTIVO_PRECO)

        reaberto = self.repo.reabrir(orcamento.id)
        self.assertEqual(reaberto.status, ENVIADO)
        self.assertEqual(reaberto.respondido_em, "")
        self.assertEqual(reaberto.motivo_recusa, "")

    def test_aprovar_sem_ter_enviado_registra_a_saida_mesmo_assim(self) -> None:
        """Cliente aprovou na hora, no balcao: a proposta saiu hoje."""
        orcamento = self._orcamento()
        aprovado = self.repo.aprovar(orcamento.id)
        self.assertEqual(aprovado.enviado_em, dia(0))


class DuplicarTestCase(OrcamentosBase):
    def test_duplicar_copia_tudo_menos_a_historia(self) -> None:
        origem = self._orcamento(
            condicao_pagamento="3x sem juros", prazo_entrega="10 dias uteis",
            desconto=100.0, observacoes="Inclui deslocamento",
            itens=[ItemOrcamento(descricao="Cabo", quantidade=60, valor_unitario=4.5,
                                 desconto=20.0, unidade="m")],
        )
        self.repo.enviar(origem.id)
        self.repo.recusar(origem.id, MOTIVO_PRECO)

        copia = self.repo.duplicar(origem.id)
        self.assertNotEqual(copia.numero, origem.numero)
        self.assertEqual(copia.cliente, origem.cliente)
        self.assertEqual(copia.condicao_pagamento, "3x sem juros")
        self.assertEqual(copia.prazo_entrega, "10 dias uteis")
        self.assertEqual(copia.desconto, 100.0)
        self.assertEqual(len(copia.itens), 1)
        self.assertEqual(copia.itens[0].desconto, 20.0)
        self.assertEqual(copia.itens[0].unidade, "m")
        # a historia nao vem junto
        self.assertEqual(copia.status, RASCUNHO)
        self.assertEqual(copia.enviado_em, "")
        self.assertEqual(copia.respondido_em, "")
        self.assertEqual(copia.motivo_recusa, "")
        self.assertEqual(copia.data, dia(0))

    def test_a_copia_nao_mexe_no_original(self) -> None:
        origem = self._orcamento()
        self.repo.aprovar(origem.id)
        self.repo.duplicar(origem.id)
        self.assertEqual(self.repo.obter(origem.id).status, APROVADO)


class FunilTestCase(OrcamentosBase):
    def _cenario(self) -> None:
        self._orcamento(cliente="Rascunho A")
        enviado = self._orcamento(cliente="Enviado B")
        self.repo.enviar(enviado.id, quando=dia(-8))
        aprovado = self._orcamento(cliente="Aprovado C",
                                   itens=[ItemOrcamento(descricao="Obra",
                                                        valor_unitario=5000.0)])
        self.repo.aprovar(aprovado.id)
        perdido = self._orcamento(cliente="Perdido D")
        self.repo.recusar(perdido.id, MOTIVO_PRECO)
        outro = self._orcamento(cliente="Perdido E")
        self.repo.recusar(outro.id, MOTIVO_CONCORRENTE)

    def test_as_etapas_do_funil(self) -> None:
        self._cenario()
        etapas = {e.status: e for e in self.repo.resumo().etapas}
        self.assertEqual(etapas[RASCUNHO].quantidade, 1)
        self.assertEqual(etapas[ENVIADO].quantidade, 1)
        self.assertEqual(etapas[APROVADO].quantidade, 1)
        self.assertEqual(etapas[RECUSADO].quantidade, 2)
        self.assertEqual(etapas[APROVADO].valor, 5000.0)

    def test_conversao_conta_so_quem_respondeu(self) -> None:
        """Somar quem ainda nao respondeu faria o numero mentir para baixo."""
        self._cenario()
        resumo = self.repo.resumo()
        self.assertEqual(resumo.respondidos, 3)
        self.assertAlmostEqual(resumo.conversao, 33.3, places=1)
        self.assertEqual(resumo.aprovados_mes, 1)
        self.assertEqual(resumo.valor_aprovado_mes, 5000.0)
        self.assertEqual(resumo.ticket_medio, 5000.0)

    def test_sem_resposta_nenhuma_a_conversao_e_zero_e_nao_quebra(self) -> None:
        self._orcamento()
        resumo = self.repo.resumo()
        self.assertEqual(resumo.conversao, 0.0)
        self.assertEqual(resumo.respondidos, 0)

    def test_por_que_voce_perde(self) -> None:
        self._cenario()
        motivos = dict((rotulo, quantidade)
                       for rotulo, quantidade, _ in self.repo.resumo().motivos)
        self.assertEqual(motivos["Achou caro"], 1)
        self.assertEqual(motivos["Comprou de outro"], 1)

    def test_o_que_esta_parado_pede_telefonema(self) -> None:
        self._cenario()
        parados = self.repo.esperando_ha_mais_de(5)
        self.assertEqual([o.cliente for o in parados], ["Enviado B"])
        self.assertEqual(parados[0].dias_esperando, 8)

    def test_o_que_vence_na_semana(self) -> None:
        perto = self._orcamento(cliente="Vence logo", validade_dias=10)
        self.repo.enviar(perto.id, quando=dia(-7))     # vence em 3 dias
        longe = self._orcamento(cliente="Vence tarde", validade_dias=60)
        self.repo.enviar(longe.id)

        vencendo = [o.cliente for o in self.repo.resumo().vencendo]
        self.assertIn("Vence logo", vencendo)
        self.assertNotIn("Vence tarde", vencendo)


class DocumentoTestCase(OrcamentosBase):
    def test_a_proposta_mostra_onde_o_desconto_entrou(self) -> None:
        orcamento = self._orcamento(
            condicao_pagamento="50% na entrada, 50% na entrega",
            prazo_entrega="10 dias uteis", validade_dias=15, desconto=100.0,
            itens=[
                ItemOrcamento(descricao="Cabo cat6", quantidade=60, valor_unitario=4.5,
                              desconto=20.0, unidade="m"),
                ItemOrcamento(descricao="Instalacao de rede", valor_unitario=1800.0),
            ],
        )
        self.repo.enviar(orcamento.id)
        texto = proposta(self.repo.obter(orcamento.id))

        self.assertIn("PROPOSTA COMERCIAL", texto)
        self.assertIn("Mercado Central", texto)
        self.assertIn("60 m x R$ 4,50", texto)
        self.assertIn("desconto nesta linha", texto)
        self.assertIn("Descontos por item", texto)
        self.assertIn("Desconto na proposta", texto)
        self.assertIn("R$ 1.950,00", texto)          # total
        self.assertIn("50% na entrada", texto)
        self.assertIn("10 dias uteis", texto)
        self.assertIn("Proposta válida até", texto)
        self.assertTrue(all(len(linha) <= 40 for linha in texto.splitlines()))

    def test_sem_desconto_o_documento_nao_mostra_linha_de_desconto(self) -> None:
        texto = proposta(self._orcamento())
        self.assertNotIn("Desconto", texto)
        self.assertIn("TOTAL", texto)

    def test_o_documento_diz_quando_a_proposta_ja_foi_respondida(self) -> None:
        orcamento = self._orcamento()
        self.repo.aprovar(orcamento.id)
        self.assertIn("*** APROVADA ***", proposta(self.repo.obter(orcamento.id)))


class MigracaoTestCase(unittest.TestCase):
    """Quem ja tinha orcamentos na versao 1 nao pode perder nada."""

    def test_v1_vira_v2_mantendo_valores_e_datas(self) -> None:
        arquivo = _arquivo("orcamentos.db")
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO orcamentos (id, numero, cliente, data, validade, status,"
            " desconto, observacoes, criado_em) VALUES (1, 'ORC-2025-0001',"
            " 'Mercado Central', '2025-11-10', '2025-11-25', 'aprovado', 50.0,"
            " 'Proposta antiga', '2025-11-10T09:00:00')"
        )
        conn.execute(
            "INSERT INTO orcamento_itens (orcamento_id, descricao, quantidade,"
            " valor_unitario) VALUES (1, 'Servico antigo', 2, 300.0)"
        )
        conn.execute(
            "INSERT INTO orcamentos (id, numero, cliente, data, status, desconto,"
            " observacoes, criado_em) VALUES (2, 'ORC-2025-0002', 'Joao',"
            " '2025-12-01', 'rascunho', 0, '', '2025-12-01T09:00:00')"
        )
        conn.execute(
            "INSERT INTO orcamento_itens (orcamento_id, descricao, quantidade,"
            " valor_unitario) VALUES (2, 'Outro servico', 1, 150.0)"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        db = open_database(arquivo)
        self.addCleanup(db.close)
        repo = OrcamentosRepository(db)
        self.assertEqual(db.schema_version, MIGRATIONS[-1].version)

        antigo = repo.obter(1)
        self.assertEqual(antigo.cliente, "Mercado Central")
        self.assertEqual(antigo.observacoes, "Proposta antiga")
        self.assertEqual(antigo.total, 550.0)
        self.assertEqual(antigo.total_gravado, 550.0)   # a coluna nova foi preenchida
        self.assertEqual(antigo.itens[0].quantidade, 2.0)
        self.assertEqual(antigo.itens[0].desconto, 0.0)
        # o que ja tinha saido ganhou as datas que o funil precisa
        self.assertEqual(antigo.enviado_em, "2025-11-10")
        self.assertEqual(antigo.respondido_em, "2025-11-10")

        rascunho = repo.obter(2)
        self.assertEqual(rascunho.enviado_em, "")
        self.assertEqual(rascunho.validade_dias, 15)

        # e o banco migrado continua rodando o funil
        repo.enviar(2)
        self.assertEqual(repo.obter(2).status, ENVIADO)
        self.assertEqual(repo.resumo().respondidos, 1)


if __name__ == "__main__":
    unittest.main()
