"""Agendamento online do lado do Hub: banco, ajustes, sincronia e a aba Online."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dumtech.apps.agenda import module as modulo_agenda
from dumtech.apps.agenda.database import MIGRATIONS, open_database
from dumtech.apps.agenda.models import AGENDADO, BLOQUEIO, CANCELADO, AgendaError, Compromisso
from dumtech.apps.agenda.online import (
    SALVAR,
    SINCRONIZAR,
    AjustesOnline,
    Dia,
    Online,
    Servico,
    Sincronia,
    config_do_servidor,
    slug_de,
)
from dumtech.apps.agenda.repository import AgendaRepository
from dumtech.core.database import Database
from dumtech.core.empresa import Empresa
from dumtech.core.online import OnlineError
from dumtech.core.paths import DataPaths

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _daqui(dias: int, hora: int = 10) -> str:
    return datetime.combine(date.today() + timedelta(days=dias), datetime.min.time()).replace(
        hour=hora).isoformat(timespec="minutes")


class ServidorFalso:
    """O servidor de mentira: guarda as chamadas e devolve o que o teste mandar."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[str, dict]] = []
        self.novas: list[dict] = []
        self.canceladas: list[str] = []
        self.erro: OnlineError | None = None

    def disponivel(self) -> bool:
        return True

    def chamar(self, funcao: str, params: dict | None = None) -> dict:
        self.chamadas.append((funcao, dict(params or {})))
        if self.erro is not None:
            raise self.erro
        if funcao == SALVAR:
            return {"ok": True, "slug": "beauty-cia", "ativo": bool(params.get("p_ativo"))}
        novas, self.novas = self.novas, []
        canceladas, self.canceladas = self.canceladas, []
        return {"ok": True, "link": True, "slug": "beauty-cia", "ativo": True,
                "novas": novas, "canceladas": canceladas}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = DataPaths(root=Path(tempfile.mkdtemp(prefix="dumtech_online_"))).ensure()
        self.banco = open_database(self.paths.app_db("agenda"))
        self.addCleanup(self.banco.close)
        self.repo = AgendaRepository(self.banco)
        self.empresa = Empresa(nome="Beauty & Cia", telefone="(11) 98765-4321",
                               endereco="Rua das Flores", numero="120", cidade="Santo André", uf="SP")


# ================================================================ o banco ===
class BancoTestCase(Base):
    def test_migration_3_num_banco_antigo_nao_perde_nada(self) -> None:
        caminho = Path(tempfile.mkdtemp()) / "agenda.db"
        antigo = Database(caminho, MIGRATIONS[:2])
        antigo.execute("INSERT INTO compromissos (titulo, cliente, inicio, criado_em)"
                       " VALUES ('Corte', 'Ana', '2026-10-20T09:00', '2026-10-01T08:00')")
        self.assertEqual(antigo.schema_version, 2)
        antigo.close()

        novo = open_database(caminho)
        self.addCleanup(novo.close)
        self.assertEqual(novo.schema_version, 3)
        compromisso = AgendaRepository(novo).listar()[0]
        self.assertEqual((compromisso.titulo, compromisso.cliente), ("Corte", "Ana"))
        self.assertEqual((compromisso.telefone, compromisso.origem, compromisso.reserva), ("", "", ""))

    def test_ocupados_nao_levam_nome_de_ninguem(self) -> None:
        self.repo.salvar(Compromisso(titulo="Corte", cliente="Ana", telefone="11999990000",
                                     inicio=_daqui(1, 9), duracao_min=45, observacoes="segredo"))
        self.repo.salvar(Compromisso(titulo="Almoço", inicio=_daqui(1, 12), tipo=BLOQUEIO))
        self.repo.salvar(Compromisso(titulo="Desistiu", inicio=_daqui(1, 15), status=CANCELADO))
        ocupados = self.repo.ocupados(date.today(), date.today() + timedelta(days=3))
        self.assertEqual(ocupados, [[_daqui(1, 9), 45, 0], [_daqui(1, 12), 60, 1]])
        self.assertNotIn("Ana", repr(ocupados))

    def test_importar_reserva_uma_vez_so(self) -> None:
        reserva = {"id": "r-1", "servico": "Corte", "inicio": _daqui(2, 14), "duracao": 60,
                   "nome": "Maria", "telefone": "11987654321", "observacao": "Primeira vez"}
        criado = self.repo.importar_reserva(reserva)
        self.assertIsNotNone(criado)
        self.assertIsNone(self.repo.importar_reserva(reserva), "a mesma reserva entrou duas vezes")
        salvo = self.repo.obter(criado.id)
        self.assertEqual((salvo.titulo, salvo.cliente, salvo.status, salvo.origem),
                         ("Corte", "Maria", AGENDADO, "link"))
        self.assertEqual(salvo.telefone, "(11) 98765-4321")
        self.assertTrue(salvo.pelo_link)
        self.assertEqual([c.id for c in self.repo.do_link_para_confirmar()], [criado.id])

    def test_cancelamento_do_cliente(self) -> None:
        criado = self.repo.importar_reserva({"id": "r-2", "servico": "Escova", "inicio": _daqui(1, 10),
                                             "duracao": 30, "nome": "Bia", "telefone": "", "observacao": ""})
        cancelado = self.repo.cancelar_reserva("r-2")
        self.assertEqual(cancelado.status, CANCELADO)
        self.assertIn("Cancelado pelo cliente", self.repo.obter(criado.id).observacoes)
        self.assertIsNone(self.repo.cancelar_reserva("r-2"), "cancelar de novo nao muda nada")
        self.assertEqual(self.repo.do_link_para_confirmar(), [])

    def test_editar_compromisso_do_link_nao_perde_a_origem(self) -> None:
        criado = self.repo.importar_reserva({"id": "r-3", "servico": "Corte", "inicio": _daqui(1, 11),
                                             "duracao": 60, "nome": "Lia", "telefone": "", "observacao": ""})
        criado.titulo = "Corte e escova"
        self.repo.salvar(criado)
        salvo = self.repo.obter(criado.id)
        self.assertEqual((salvo.origem, salvo.reserva), ("link", "r-3"))


# ============================================================== os ajustes ===
class AjustesTestCase(Base):
    def test_o_padrao_ja_serve(self) -> None:
        ajustes = AjustesOnline.padrao()
        ajustes.validar()
        self.assertEqual(ajustes.semana[0].intervalos(), [[540, 720], [780, 1080]])
        self.assertEqual(ajustes.semana[5].intervalos(), [[540, 780]])
        self.assertEqual(ajustes.semana[6].intervalos(), [])

    def test_validacao_fala_portugues(self) -> None:
        casos = [
            (AjustesOnline(servicos=[], semana=AjustesOnline.padrao().semana), "serviço"),
            (AjustesOnline(servicos=[Servico("s1", " ")], semana=AjustesOnline.padrao().semana), "nome"),
            (AjustesOnline(servicos=[Servico("s1", "Corte")], semana=[Dia(aberto=False)] * 7), "Abra"),
            (AjustesOnline(servicos=[Servico("s1", "Corte")],
                           semana=[Dia(abre=600, fecha=540)] + [Dia()] * 6), "fechar"),
            (AjustesOnline(servicos=[Servico("s1", "Corte")],
                           semana=[Dia(almoco_de=1200, almoco_ate=1260)] + [Dia()] * 6), "almoço"),
        ]
        for ajustes, trecho in casos:
            with self.assertRaises(AgendaError) as erro:
                ajustes.validar()
            self.assertIn(trecho, str(erro.exception))

    def test_ida_e_volta_pelo_banco(self) -> None:
        online = Online(self.repo)
        self.assertFalse(online.criado)
        ajustes = AjustesOnline.padrao()
        ajustes.servicos.append(Servico("s2", "Escova", 30, 45.0))
        ajustes.cor = "rosa"
        online.salvar(ajustes, ativo=False)
        lido = Online(self.repo)
        self.assertTrue(lido.criado)
        self.assertFalse(lido.ativo)
        self.assertEqual(lido.ajustes(), ajustes)

    def test_slug_e_configuracao(self) -> None:
        self.assertEqual(slug_de("Beauty & Cia"), "beauty-cia")
        self.assertEqual(slug_de("Salão da Ána!"), "salao-da-ana")
        config = config_do_servidor(AjustesOnline.padrao(), self.empresa)
        self.assertEqual(config["empresa"]["whatsapp"], "5511987654321")
        self.assertEqual(config["empresa"]["endereco"], "Rua das Flores, 120 · Santo André/SP")
        self.assertEqual(len(config["semana"]), 7)
        self.assertEqual(config["servicos"][0], {"id": "s1", "nome": "Atendimento", "duracao": 60, "preco": None})


# ============================================================= a sincronia ===
class SincroniaTestCase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.servidor = ServidorFalso()
        self.agora = 0.0
        self.sincronia = Sincronia(self.paths, lambda: self.empresa, relogio=lambda: self.agora)

    def conversar(self, agora: float | None = None):
        if agora is not None:
            self.agora = agora
        pedido = self.sincronia.preparar()
        if pedido is None:
            return None
        funcao, params = pedido
        try:
            resposta = self.servidor.chamar(funcao, params)
        except OnlineError as erro:
            self.sincronia.falhou(funcao, erro)
            return funcao, params, None
        return funcao, params, self.sincronia.aplicar(funcao, params, resposta)

    def test_sem_link_criado_nada_sai_do_computador(self) -> None:
        self.assertIsNone(self.sincronia.preparar())

    def test_ciclo_completo(self) -> None:
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)

        # 1. publica a configuracao (e guarda o endereco)
        funcao, params, _ = self.conversar()
        self.assertEqual(funcao, SALVAR)
        self.assertEqual(params["p_sugestao"], "beauty-cia")
        self.assertEqual(Online(self.repo).link, "https://dumtechsolution.com/agendar/beauty-cia")

        # 2. publica os ocupados
        funcao, params, _ = self.conversar()
        self.assertEqual(funcao, SINCRONIZAR)
        self.assertEqual(params["p_ocupados"], [])
        self.agora = 1.0
        self.assertIsNone(self.sincronia.preparar(), "sem mudanca, espera o intervalo")

        # 3. chega uma reserva: entra na agenda e avisa
        self.servidor.novas = [{"id": "r-9", "servico": "Atendimento", "inicio": _daqui(2, 15),
                                "duracao": 60, "nome": "Maria", "telefone": "11987654321",
                                "observacao": ""}]
        funcao, params, resultado = self.conversar(agora=100.0)
        self.assertTrue(resultado.mudou)
        self.assertIn("Maria", resultado.avisos[0])
        self.assertTrue(resultado.de_novo, "tem recebimento para confirmar")

        # 4. confirma o recebimento JUNTO com os ocupados novos
        funcao, params, resultado = self.conversar(agora=101.0)
        self.assertEqual(params["p_recebidas"], ["r-9"])
        self.assertEqual(params["p_ocupados"], [[_daqui(2, 15), 60, 0]])
        self.assertFalse(resultado.de_novo)

        # 5. o cliente cancela pelo link
        self.servidor.canceladas = ["r-9"]
        funcao, params, resultado = self.conversar(agora=200.0)
        self.assertIn("Cancelado pelo cliente", resultado.avisos[0])
        funcao, params, _ = self.conversar(agora=201.0)
        self.assertEqual(params["p_canceladas"], ["r-9"])
        self.assertEqual(params["p_ocupados"], [], "o horario cancelado sai dos ocupados")

    def test_mudar_os_ajustes_publica_de_novo(self) -> None:
        online = Online(self.repo)
        online.salvar(AjustesOnline.padrao(), ativo=True)
        self.conversar()
        self.conversar()
        ajustes = online.ajustes()
        ajustes.vagas = 3
        online.salvar(ajustes, ativo=True)
        funcao, params, _ = self.conversar(agora=10.0)
        self.assertEqual(funcao, SALVAR)
        self.assertEqual(params["p_config"]["vagas"], 3)

    def test_sem_internet_fica_salvo_e_espera(self) -> None:
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        self.servidor.erro = OnlineError("Sem internet agora.", "sem_internet")
        self.conversar(agora=0.0)
        self.assertEqual(Online(self.repo).erro, "Sem internet agora.")
        self.agora = 10.0
        self.assertIsNone(self.sincronia.preparar(), "nao martela o servidor")
        self.servidor.erro = None
        self.agora = 1e9
        self.assertIsNotNone(self.sincronia.preparar())


# ============================================================ avisos e tela ===
class AvisosTestCase(Base):
    def test_inicio_avisa_o_que_falta_confirmar(self) -> None:
        self.repo.importar_reserva({"id": "r-5", "servico": "Corte", "inicio": _daqui(1, 10),
                                    "duracao": 60, "nome": "Maria", "telefone": "", "observacao": ""})
        avisos = [a for a in modulo_agenda.avisos(self.paths, None) if a.tipo == "link_para_confirmar"]
        self.assertEqual(len(avisos), 1)
        self.assertIn("1 agendamento do link", avisos[0].titulo)


class TelaOnlineTestCase(Base):
    def tela(self, servidor=None):
        from dumtech.apps.agenda.ui.online_view import OnlineView

        tela = OnlineView(self.repo, servidor=servidor, empresa=self.empresa, paths=self.paths)
        self.addCleanup(tela.deleteLater)
        return tela

    def esperar(self, condicao) -> None:
        import time

        limite = time.monotonic() + 5
        while not condicao() and time.monotonic() < limite:
            QApplication.processEvents()
            time.sleep(0.01)

    def test_primeira_vez_mostra_o_convite(self) -> None:
        tela = self.tela(ServidorFalso())
        self.assertFalse(tela.cartao_vazio.isHidden())
        self.assertTrue(tela.conteudo.isHidden())

    def test_criar_publica_e_mostra_o_link(self) -> None:
        servidor = ServidorFalso()
        tela = self.tela(servidor)
        tela.criar()
        self.esperar(lambda: servidor.chamadas and not tela._publicando)
        self.assertEqual(servidor.chamadas[0][0], SALVAR)
        self.assertIn("dumtechsolution.com/agendar/beauty-cia", tela.endereco.text())
        self.assertTrue(tela.botao_copiar.isEnabled())

    def test_erro_de_preenchimento_nao_sai_daqui(self) -> None:
        servidor = ServidorFalso()
        tela = self.tela(servidor)
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        tela.refresh()
        tela.servicos.preencher([Servico("s1", "")])
        tela.salvar()
        self.assertIn("nome", tela.aviso.text())
        self.assertEqual(servidor.chamadas, [])

    def test_sem_licenca_salva_e_explica(self) -> None:
        tela = self.tela(None)
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        tela.refresh()
        tela.salvar()
        self.assertIn("licença", tela.aviso.text())


if __name__ == "__main__":
    unittest.main()
