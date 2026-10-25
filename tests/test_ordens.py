"""Regras do servico: esteira, aprovacao, itens, garantia e comprovantes."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from dumtech.apps.ordens.database import MIGRATIONS, open_database
from dumtech.apps.ordens.models import (
    ABERTA,
    AGUARDANDO,
    ANDAMENTO,
    CANCELADA,
    CONCLUIDA,
    ENTREGUE,
    PECA,
    SERVICO,
    ItemOS,
    Ordem,
    OrdemError,
)
from dumtech.apps.ordens.recibo import entrada, entrega
from dumtech.apps.ordens.repository import OrdensRepository


def _arquivo(nome: str) -> Path:
    return Path(tempfile.mkdtemp()) / nome


def dia(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


class OrdensBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = open_database(_arquivo("ordens.db"))
        self.repo = OrdensRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def _ordem(self, **campos) -> Ordem:
        dados = dict(
            numero=self.repo.proximo_numero(),
            cliente="Joao da Silva",
            telefone="63999990000",
            equipamento="Notebook Dell G15",
            defeito="Nao liga",
        )
        dados.update(campos)
        return self.repo.salvar(Ordem(**dados))

    def _ate_concluir(self, ordem: Ordem) -> Ordem:
        self.repo.avancar(ordem.id)                      # -> aguardando
        self.repo.aprovar(ordem.id, "Joao da Silva")     # -> andamento
        return self.repo.avancar(ordem.id)               # -> concluida


class EsteiraTestCase(OrdensBase):
    def test_a_ordem_nasce_aberta_e_com_historico(self) -> None:
        ordem = self._ordem()
        self.assertEqual(ordem.status, ABERTA)
        self.assertEqual(len(ordem.historico), 1)
        self.assertEqual(ordem.historico[0].status, ABERTA)
        self.assertTrue(ordem.historico[0].criado_em)

    def test_cada_passo_deixa_registro_com_hora(self) -> None:
        ordem = self._ordem()
        self.repo.avancar(ordem.id)
        self.repo.aprovar(ordem.id, "Joao da Silva")
        self.repo.avancar(ordem.id)
        self.repo.entregar(ordem.id, "Joao da Silva")

        historico = self.repo.obter(ordem.id).historico
        self.assertEqual(
            [evento.status for evento in historico],
            [ABERTA, AGUARDANDO, ANDAMENTO, CONCLUIDA, ENTREGUE],
        )
        self.assertIn("aprovado por Joao da Silva", historico[2].observacao)
        self.assertIn("Entregue para Joao da Silva", historico[4].observacao)

    def test_nao_se_comeca_o_servico_sem_o_cliente_aprovar(self) -> None:
        ordem = self._ordem()
        self.repo.avancar(ordem.id)   # aberta -> aguardando aprovacao
        self.assertEqual(self.repo.obter(ordem.id).status, AGUARDANDO)

        with self.assertRaises(OrdemError) as erro:
            self.repo.avancar(ordem.id)
        self.assertIn("aprovou", str(erro.exception))

    def test_aprovacao_guarda_quem_e_quando(self) -> None:
        ordem = self._ordem()
        self.repo.avancar(ordem.id)
        aprovada = self.repo.aprovar(ordem.id, "Maria (esposa)")

        self.assertEqual(aprovada.status, ANDAMENTO)
        self.assertTrue(aprovada.aprovada)
        self.assertEqual(aprovada.aprovado_por, "Maria (esposa)")
        self.assertEqual(aprovada.aprovado_em, dia(0))

    def test_aprovacao_sem_nome_e_recusada(self) -> None:
        ordem = self._ordem()
        self.repo.avancar(ordem.id)
        with self.assertRaises(OrdemError):
            self.repo.aprovar(ordem.id, "   ")

    def test_nao_se_entrega_o_que_nao_ficou_pronto(self) -> None:
        ordem = self._ordem()
        with self.assertRaises(OrdemError) as erro:
            self.repo.entregar(ordem.id)
        self.assertIn("não está concluída", str(erro.exception))

    def test_entrega_encerra_a_esteira(self) -> None:
        ordem = self._ate_concluir(self._ordem())
        entregue = self.repo.entregar(ordem.id, "Joao da Silva")

        self.assertEqual(entregue.status, ENTREGUE)
        self.assertEqual(entregue.entregue_em, dia(0))
        self.assertFalse(entregue.aberta)
        with self.assertRaises(OrdemError):
            self.repo.avancar(ordem.id)

    def test_cancelamento_exige_motivo_e_fica_no_historico(self) -> None:
        ordem = self._ordem()
        with self.assertRaises(OrdemError):
            self.repo.cancelar(ordem.id, "  ")

        cancelada = self.repo.cancelar(ordem.id, "Cliente desistiu do conserto")
        self.assertEqual(cancelada.status, CANCELADA)
        self.assertIn("Cliente desistiu", cancelada.historico[-1].observacao)

    def test_reabrir_traz_de_volta_sem_perder_o_passado(self) -> None:
        ordem = self._ate_concluir(self._ordem())
        self.repo.entregar(ordem.id)
        reaberta = self.repo.reabrir(ordem.id, "Voltou com o mesmo defeito")

        self.assertEqual(reaberta.status, ANDAMENTO)
        self.assertEqual(reaberta.entregue_em, "")
        self.assertIn("Voltou com o mesmo defeito", reaberta.historico[-1].observacao)
        self.assertGreaterEqual(len(reaberta.historico), 6)

    def test_ordem_entregue_nao_pode_ser_apagada(self) -> None:
        ordem = self._ate_concluir(self._ordem())
        self.repo.entregar(ordem.id)
        with self.assertRaises(OrdemError):
            self.repo.excluir(ordem.id)


class ItensTestCase(OrdensBase):
    def _com_itens(self) -> Ordem:
        return self._ordem(itens=[
            ItemOS(tipo=PECA, descricao="Placa mae", quantidade=1, valor_unitario=680.0),
            ItemOS(tipo=PECA, descricao="Pasta termica", quantidade=1, valor_unitario=25.0),
            ItemOS(tipo=SERVICO, descricao="Mao de obra", quantidade=2, valor_unitario=90.0),
        ])

    def test_o_total_vem_dos_itens(self) -> None:
        ordem = self._com_itens()
        self.assertEqual(ordem.subtotal, 885.0)
        self.assertEqual(ordem.total, 885.0)
        self.assertEqual(self.repo.obter(ordem.id).valor, 885.0)

    def test_peca_e_servico_somam_separado(self) -> None:
        """A conta que diz se o servico valeu a pena."""
        ordem = self._com_itens()
        self.assertEqual(ordem.total_pecas, 705.0)
        self.assertEqual(ordem.total_servicos, 180.0)

    def test_desconto_sai_do_total(self) -> None:
        ordem = self._ordem(
            desconto=85.0,
            itens=[ItemOS(tipo=SERVICO, descricao="Formatacao", valor_unitario=185.0)],
        )
        self.assertEqual(ordem.total, 100.0)
        self.assertEqual(self.repo.obter(ordem.id).valor, 100.0)

    def test_desconto_maior_que_os_itens_e_recusado(self) -> None:
        with self.assertRaises(OrdemError):
            self._ordem(
                desconto=500.0,
                itens=[ItemOS(descricao="Servico", valor_unitario=100.0)],
            )

    def test_item_sem_descricao_e_recusado(self) -> None:
        with self.assertRaises(OrdemError):
            self._ordem(itens=[ItemOS(descricao="   ", valor_unitario=10.0)])

    def test_servico_simples_continua_com_valor_digitado(self) -> None:
        """Sem itens, o valor e o que o balcao escreveu."""
        ordem = self._ordem(valor=150.0)
        self.assertEqual(ordem.total, 150.0)
        self.assertEqual(self.repo.obter(ordem.id).valor, 150.0)

    def test_editar_troca_os_itens_inteiros(self) -> None:
        ordem = self._com_itens()
        salva = self.repo.obter(ordem.id)
        salva.itens = [ItemOS(tipo=SERVICO, descricao="So limpeza", valor_unitario=80.0)]
        self.repo.salvar(salva)

        atual = self.repo.obter(ordem.id)
        self.assertEqual(len(atual.itens), 1)
        self.assertEqual(atual.valor, 80.0)


class GarantiaTestCase(OrdensBase):
    def test_a_garantia_conta_da_entrega_nao_da_conclusao(self) -> None:
        ordem = self._ate_concluir(self._ordem(garantia_dias=90))
        self.assertEqual(ordem.garantia_ate, "")   # ainda nao foi entregue

        entregue = self.repo.entregar(ordem.id)
        limite = (date.today() + timedelta(days=90)).isoformat()
        self.assertEqual(entregue.garantia_ate, limite)
        self.assertTrue(entregue.na_garantia)

    def test_garantia_vencida(self) -> None:
        ordem = self._ate_concluir(self._ordem(garantia_dias=1))
        entregue = self.repo.entregar(ordem.id)
        entregue.entregue_em = dia(-30)
        self.repo.salvar(entregue)
        self.assertFalse(self.repo.obter(ordem.id).na_garantia)

    def test_sem_garantia_nao_inventa_data(self) -> None:
        ordem = self._ate_concluir(self._ordem(garantia_dias=0))
        entregue = self.repo.entregar(ordem.id)
        self.assertEqual(entregue.garantia_ate, "")
        self.assertFalse(entregue.na_garantia)

    def test_filtro_de_garantia_acha_so_quem_esta_coberto(self) -> None:
        coberta = self._ate_concluir(self._ordem(garantia_dias=90))
        self.repo.entregar(coberta.id)
        em_aberto = self._ordem(cliente="Outro cliente")

        achadas = [o.id for o in self.repo.listar(na_garantia=True)]
        self.assertEqual(achadas, [coberta.id])
        self.assertNotIn(em_aberto.id, achadas)


class QuadroTestCase(OrdensBase):
    def test_faixas_do_quadro(self) -> None:
        aberta = self._ordem(cliente="Cliente A")
        aguardando = self._ordem(cliente="Cliente B")
        self.repo.avancar(aguardando.id)
        andamento = self._ordem(cliente="Cliente C")
        self.repo.avancar(andamento.id)
        self.repo.aprovar(andamento.id, "Cliente C")
        entregue = self._ate_concluir(self._ordem(cliente="Cliente D"))
        self.repo.entregar(entregue.id)

        faixas = self.repo.por_etapa()
        self.assertEqual([o.id for o in faixas[ABERTA]], [aberta.id])
        self.assertEqual([o.id for o in faixas[AGUARDANDO]], [aguardando.id])
        self.assertEqual([o.id for o in faixas[ANDAMENTO]], [andamento.id])
        # entregue saiu do quadro
        self.assertNotIn(ENTREGUE, faixas)

    def test_atrasada_e_so_o_que_ainda_esta_em_aberto(self) -> None:
        atrasada = self._ordem(prazo=dia(-2))
        self.assertTrue(self.repo.obter(atrasada.id).atrasada)

        pronta = self._ate_concluir(self._ordem(prazo=dia(-2)))
        self.repo.entregar(pronta.id)
        self.assertFalse(self.repo.obter(pronta.id).atrasada)

    def test_resumo_do_painel(self) -> None:
        self._ordem(cliente="Na fila")
        aguardando = self._ordem(cliente="Esperando resposta")
        self.repo.avancar(aguardando.id)
        entregue = self._ate_concluir(self._ordem(
            cliente="Pronta",
            itens=[ItemOS(tipo=PECA, descricao="Tela", valor_unitario=400.0),
                   ItemOS(tipo=SERVICO, descricao="Troca", valor_unitario=120.0)],
        ))
        self.repo.entregar(entregue.id)

        resumo = self.repo.resumo()
        self.assertEqual(resumo.abertas, 1)
        self.assertEqual(resumo.aguardando, 1)
        self.assertEqual(resumo.concluidas_mes, 1)
        self.assertEqual(resumo.valor_mes, 520.0)
        self.assertEqual(resumo.pecas_mes, 400.0)
        self.assertEqual(resumo.servicos_mes, 120.0)
        self.assertEqual([o.cliente for o in resumo.aguardando_lista],
                         ["Esperando resposta"])


class ComprovanteTestCase(OrdensBase):
    def test_o_papel_de_entrada_registra_o_que_entrou(self) -> None:
        ordem = self._ordem(
            acessorios="Carregador\nCapa",
            condicao="Risco na tampa e tecla F5 solta",
            prazo=dia(3),
        )
        texto = entrada(ordem)

        self.assertIn("COMPROVANTE DE ENTRADA", texto)
        self.assertIn("[X] Carregador", texto)
        self.assertIn("[X] Capa", texto)
        self.assertIn("Risco na tampa", texto)
        self.assertIn("Nao liga", texto)
        self.assertIn("Assinatura do cliente", texto)
        self.assertTrue(all(len(linha) <= 40 for linha in texto.splitlines()))

    def test_entrada_de_item_sem_acessorio_diz_isso_em_vez_de_ficar_em_branco(self) -> None:
        """Ficou com o item do cliente: o papel registra que nada veio junto."""
        texto = entrada(self._ordem())
        self.assertIn("Nenhum acessório recebido", texto)

    def test_orcamento_pendente_avisa_que_o_servico_espera_aprovacao(self) -> None:
        texto = entrada(self._ordem(valor=300.0))
        self.assertIn("aprovação do orçamento", " ".join(texto.split()))

    def test_servico_ja_aprovado_no_balcao_nao_fala_de_aprovacao(self) -> None:
        """Lava-jato, lavanderia, chaveiro: cobra e faz. Nao ha o que aprovar.

        O aviso saia sempre, e no comprovante de quem nao orca era mentira
        impressa. Agora ele depende de haver um valor na mao do cliente sem
        aprovacao registrada.
        """
        ordem = self._ordem(valor=45.0, defeito="Lavar 3 kg de roupa",
                            equipamento="", aprovado_em="2026-01-10",
                            aprovado_por="Maria")
        self.assertNotIn("aprovacao", entrada(ordem))

    def test_servico_sem_item_nao_fala_de_acessorio(self) -> None:
        """Quem instala, lava ou faz chave nao recebe nada - e nem pergunta.

        A linha "Nenhum acessorio recebido" protege quem fica com o aparelho do
        cliente. Sem item nenhum na loja, ela so faz o cliente perguntar que
        acessorio seria esse.
        """
        texto = entrada(self._ordem(equipamento="", defeito="Instalar o ar da sala"))
        self.assertNotIn("acessorio", texto.lower())
        self.assertIn("Instalar o ar da sala", texto)

    def test_o_papel_de_entrega_presta_contas_e_abre_a_garantia(self) -> None:
        ordem = self._ordem(
            diagnostico="Placa mae com curto no circuito de carga",
            garantia_dias=90,
            itens=[ItemOS(tipo=PECA, descricao="Placa mae", valor_unitario=680.0),
                   ItemOS(tipo=SERVICO, descricao="Mao de obra", valor_unitario=180.0)],
        )
        self.repo.avancar(ordem.id)
        self.repo.aprovar(ordem.id, "Joao da Silva")
        self.repo.avancar(ordem.id)
        entregue = self.repo.entregar(ordem.id, "Joao da Silva")

        texto = entrega(entregue)
        self.assertIn("COMPROVANTE DE ENTREGA", texto)
        self.assertIn("Placa mae com curto", texto)
        self.assertIn("Material: Placa mae", texto)
        self.assertIn("R$ 860,00", texto)
        self.assertIn("aprovado por Joao da Silva", texto)
        self.assertIn("Garantia (90 dias)", texto)
        # a bobina quebra em 40 colunas, entao a frase da garantia e conferida
        # sem as quebras - senao o teste prende o texto no comprimento de hoje
        self.assertIn("Não cobre mau uso", " ".join(texto.split()))
        self.assertTrue(all(len(linha) <= 40 for linha in texto.splitlines()))

    def test_entrega_sem_garantia_diz_que_nao_tem(self) -> None:
        ordem = self._ate_concluir(self._ordem(garantia_dias=0))
        texto = entrega(self.repo.entregar(ordem.id))
        self.assertIn("Sem garantia para este serviço", texto)


class MigracaoTestCase(unittest.TestCase):
    """Quem ja tinha ordens na versao 1 nao pode perder nada."""

    def test_v1_vira_v2_com_historico_e_entrega(self) -> None:
        arquivo = _arquivo("ordens.db")
        conn = sqlite3.connect(arquivo)
        conn.executescript(MIGRATIONS[0].statements[0])
        conn.execute(
            "INSERT INTO ordens (id, numero, cliente, telefone, equipamento, defeito,"
            " diagnostico, servico, valor, status, tecnico, aberta_em, prazo,"
            " concluida_em, observacoes, criado_em)"
            " VALUES (1, 'OS-2025-0001', 'Maria Souza', '6399999000', 'Impressora',"
            " 'Nao puxa papel', 'Rolete gasto', 'Troca do rolete', 190.0, 'entregue',"
            " 'Equipe', '2025-11-02', '2025-11-05', '2025-11-04', 'ok',"
            " '2025-11-02T09:00:00')"
        )
        conn.execute(
            "INSERT INTO ordens (id, numero, cliente, equipamento, defeito, valor,"
            " status, aberta_em, criado_em)"
            " VALUES (2, 'OS-2025-0002', 'Joao', 'Notebook', 'Lento', 120.0,"
            " 'aberta', '2025-12-01', '2025-12-01T09:00:00')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        db = open_database(arquivo)
        self.addCleanup(db.close)
        repo = OrdensRepository(db)
        # sobe ate a ultima migracao existente, seja qual for o numero de hoje
        self.assertEqual(db.schema_version, MIGRATIONS[-1].version)

        antiga = repo.obter(1)
        self.assertEqual(antiga.cliente, "Maria Souza")
        self.assertEqual(antiga.valor, 190.0)
        self.assertEqual(antiga.status, ENTREGUE)
        # a entrega ganhou data, e a garantia passa a valer a partir dela
        self.assertEqual(antiga.entregue_em, "2025-11-04")
        self.assertEqual(antiga.garantia_dias, 90)
        # e ninguem nasce sem passado
        self.assertEqual(len(antiga.historico), 1)
        self.assertIn("anterior a atualizacao", antiga.historico[0].observacao)

        aberta = repo.obter(2)
        self.assertEqual(aberta.status, ABERTA)
        self.assertEqual(aberta.entregue_em, "")
        self.assertEqual(aberta.itens, [])
        self.assertEqual(aberta.acessorios, "")

        # e o banco migrado continua rodando a esteira
        repo.avancar(2)
        repo.aprovar(2, "Joao")
        self.assertEqual(repo.obter(2).status, ANDAMENTO)


if __name__ == "__main__":
    unittest.main()
