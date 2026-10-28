"""Agendamento online do lado do Hub: banco, ajustes, sincronia e a aba Online."""

from __future__ import annotations

import json
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
    horarios_no_dia,
    passo_padrao,
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
        self.assertEqual(config["servicos"][0], {"id": "s1", "nome": "Atendimento", "duracao": 60,
                                                 "preco": None, "passo": 30})


# ============================================= cada servico no tempo dele ===
class TempoDeCadaServicoTestCase(Base):
    """Pedido de cliente: a barba e de 15 minutos, entao aparece de 15 em 15."""

    def test_o_padrao_segue_a_duracao_sem_passar_do_passo_do_link(self) -> None:
        self.assertEqual(passo_padrao(15), 15)
        self.assertEqual(passo_padrao(30), 30)
        self.assertEqual(passo_padrao(60), 30, "o longo continua como o link mandava")
        self.assertEqual(passo_padrao(60, limite=60), 60)
        self.assertEqual(passo_padrao(25), 20, "arredonda para um passo da lista")
        self.assertEqual(passo_padrao(5), 10)

    def test_link_de_antes_ganha_o_tempo_de_cada_servico(self) -> None:
        # gravado pela 1.5.2: nenhum servico tem o proprio passo
        antigo = {"servicos": [{"id": "s1", "nome": "Barba", "duracao": 15, "preco": None},
                               {"id": "s2", "nome": "Corte e barba", "duracao": 60, "preco": None}],
                  "passo": 30}
        ajustes = AjustesOnline.de_json(json.dumps(antigo))
        self.assertEqual([ajustes.passo_de(s) for s in ajustes.servicos], [15, 30])
        config = config_do_servidor(ajustes, self.empresa)
        self.assertEqual([s["passo"] for s in config["servicos"]], [15, 30])

    def test_o_escolhido_vale_e_viaja(self) -> None:
        ajustes = AjustesOnline.padrao()
        ajustes.servicos = [Servico("s1", "Corte e barba", 60, passo=60)]
        ajustes.validar()
        self.assertEqual(config_do_servidor(ajustes, self.empresa)["servicos"][0]["passo"], 60)

    def test_passo_fora_da_lista_nao_passa(self) -> None:
        ajustes = AjustesOnline.padrao()
        ajustes.servicos = [Servico("s1", "Barba", 15, passo=7)]
        with self.assertRaises(AgendaError) as erro:
            ajustes.validar()
        self.assertIn("Barba", str(erro.exception))

    def test_horarios_do_dia_sao_a_conta_do_servidor(self) -> None:
        manha_e_tarde = [[540, 720], [780, 1080]]
        barba = horarios_no_dia(manha_e_tarde, 15, 15)
        self.assertEqual(barba[:4], [540, 555, 570, 585])
        self.assertEqual(len(barba), 32)
        self.assertEqual(len(horarios_no_dia(manha_e_tarde, 60, 30)), 14)
        self.assertEqual(horarios_no_dia([[540, 600]], 90, 15), [])

    def test_servicos_antes_do_link_nao_criam_o_link(self) -> None:
        online = Online(self.repo)
        online.salvar_servicos([Servico("s1", "Barba", 15, passo=15)])
        self.assertFalse(online.criado, "salvar servicos nao pode por link nenhum no ar")
        self.assertEqual(online.ajustes().servicos[0].nome, "Barba")
        self.assertIsNone(Sincronia(self.paths, lambda: self.empresa).preparar())

    def test_salvar_servicos_nao_mexe_no_resto(self) -> None:
        online = Online(self.repo)
        ajustes = AjustesOnline.padrao()
        ajustes.cor = "rosa"
        online.salvar(ajustes, ativo=False)
        online.salvar_servicos([Servico("s1", "Barba", 15, passo=15)])
        lido = online.ajustes()
        self.assertEqual(lido.cor, "rosa")
        self.assertTrue(online.criado)
        self.assertFalse(online.ativo, "o link pausado continua pausado")
        self.assertEqual([s.nome for s in lido.servicos], ["Barba"])

    def test_salvar_servicos_confere_antes(self) -> None:
        with self.assertRaises(AgendaError):
            Online(self.repo).salvar_servicos([])


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

    def test_o_hub_aberto_ve_o_agendamento_em_ate_20_segundos(self) -> None:
        """Ninguem precisa reabrir o Hub para ver quem marcou pelo link."""
        from dumtech.hub.main_window import HubWindow

        tique = HubWindow.ONLINE_INTERVALO_MS / 1000
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        self.conversar()                      # publica a configuracao
        self.conversar()                      # e os ocupados (instante 0)
        self.servidor.novas = [{"id": "r-1", "servico": "Atendimento", "inicio": _daqui(1, 9),
                                "duracao": 60, "nome": "Ana", "telefone": "11987654321",
                                "observacao": ""}]
        instante, conversa = 0.0, None
        while conversa is None:
            instante += tique + 0.4           # o relogio do Hub sempre atrasa um pouco
            conversa = self.conversar(agora=instante)
        self.assertTrue(conversa[2].mudou)
        self.assertLessEqual(instante, 21.0)

        # e o ritmo cabe no limite do servidor (240 por hora, com folga para
        # as confirmacoes): ver dumtech_agenda_sincronizar
        voltas = -(-Sincronia.INTERVALO_S // tique)
        self.assertLessEqual(3600 / (voltas * tique), 200)

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


def _esperar(condicao) -> None:
    import time

    limite = time.monotonic() + 5
    while not condicao() and time.monotonic() < limite:
        QApplication.processEvents()
        time.sleep(0.01)


def _escolher(combo, valor) -> None:
    combo.setCurrentIndex(combo.findData(valor))


class TelaOnlineTestCase(Base):
    def tela(self, servidor=None):
        from dumtech.apps.agenda.ui.online_view import OnlineView

        tela = OnlineView(self.repo, servidor=servidor, empresa=self.empresa, paths=self.paths)
        self.addCleanup(tela.deleteLater)
        return tela

    def esperar(self, condicao) -> None:
        _esperar(condicao)

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
        tela.horario.preencher([Dia(abre=600, fecha=540)] + [Dia()] * 6)
        tela.salvar()
        self.assertIn("fechar", tela.aviso.text())
        self.assertEqual(servidor.chamadas, [])

    def test_sem_licenca_salva_e_explica(self) -> None:
        tela = self.tela(None)
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        tela.refresh()
        tela.salvar()
        self.assertIn("licença", tela.aviso.text())

    def test_criar_aproveita_os_servicos_ja_montados(self) -> None:
        Online(self.repo).salvar_servicos([Servico("s1", "Barba", 15, passo=15)])
        servidor = ServidorFalso()
        tela = self.tela(servidor)
        self.assertFalse(tela.cartao_vazio.isHidden(), "servico montado nao e link criado")
        tela.criar()
        self.esperar(lambda: servidor.chamadas and not tela._publicando)
        servicos = servidor.chamadas[0][1]["p_config"]["servicos"]
        self.assertEqual([(s["nome"], s["passo"]) for s in servicos], [("Barba", 15)])

    def test_salvar_aqui_nao_apaga_os_servicos_da_outra_aba(self) -> None:
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        tela = self.tela(None)
        # a aba Servicos grava com a aba Online ja aberta e preenchida
        Online(self.repo).salvar_servicos([Servico("s1", "Barba", 15, passo=15)])
        tela.salvar()
        self.assertEqual([s.nome for s in Online(self.repo).ajustes().servicos], ["Barba"])


class TelaServicosTestCase(Base):
    """A aba Servicos: cada servico com o proprio "Horarios a cada"."""

    def tela(self):
        from dumtech.apps.agenda.ui.servicos_view import ServicosView

        tela = ServicosView(self.repo)
        self.addCleanup(tela.deleteLater)
        return tela

    def criar_link(self, servicos) -> None:
        ajustes = AjustesOnline.padrao()
        ajustes.servicos = servicos
        Online(self.repo).salvar(ajustes, ativo=True)

    def test_cada_servico_mostra_o_tempo_e_como_fica_no_link(self) -> None:
        self.criar_link([Servico("s1", "Barba", 15), Servico("s2", "Corte e barba", 60)])
        barba, longo = self.tela().editor.linhas
        self.assertEqual((barba.passo.currentData(), longo.passo.currentData()), (15, 30))
        self.assertIn("Segunda: 09:00, 09:15, 09:30, 09:45…", barba.previa.text())
        self.assertIn("32 horários", barba.previa.text())
        self.assertIn("09:00, 09:30, 10:00, 10:30…", longo.previa.text())

    def test_trocar_a_duracao_leva_o_tempo_junto(self) -> None:
        tela = self.tela()
        tela.editor.botao_mais.click()
        linha = tela.editor.linhas[-1]
        self.assertEqual(linha.passo.currentData(), 30)
        _escolher(linha.duracao, 15)
        self.assertEqual(linha.passo.currentData(), 15, "barba de 15 min, de 15 em 15")
        self.assertIn("09:15", linha.previa.text())
        # o que o dono escolheu a mao fica
        _escolher(linha.passo, 30)
        _escolher(linha.duracao, 45)
        self.assertEqual(linha.passo.currentData(), 30)

    def test_servico_que_nao_cabe_avisa(self) -> None:
        tela = self.tela()
        tela.editor.adicionar(Servico("s9", "Dia de noiva", 480))
        previa = tela.editor.linhas[-1].previa
        self.assertIn("Não cabe", previa.text())
        self.assertEqual(previa.property("tone"), "warning")

    def test_salvar_grava_o_tempo_e_pede_para_publicar(self) -> None:
        self.criar_link([Servico("s1", "Barba", 15)])
        tela = self.tela()
        pedidos = []
        tela.pedir_publicacao.connect(lambda: pedidos.append(1))
        _escolher(tela.editor.linhas[0].passo, 20)
        tela.salvar()
        self.assertEqual(pedidos, [1])
        self.assertEqual(Online(self.repo).ajustes().servicos[0].passo, 20)
        tela.mostrar_publicacao(True, "Publicado. Quem abrir o link já vê o que você mudou.")
        self.assertIn("Publicado", tela.aviso.text())

    def test_sem_link_so_guarda(self) -> None:
        tela = self.tela()
        self.assertEqual(tela.botao_salvar.text(), "Salvar")
        pedidos = []
        tela.pedir_publicacao.connect(lambda: pedidos.append(1))
        tela.salvar()
        self.assertEqual(pedidos, [])
        self.assertFalse(Online(self.repo).criado)
        self.assertIn("aba Online", tela.aviso.text())

    def test_erro_de_preenchimento_nao_sai_daqui(self) -> None:
        self.criar_link([Servico("s1", "Barba", 15)])
        tela = self.tela()
        pedidos = []
        tela.pedir_publicacao.connect(lambda: pedidos.append(1))
        tela.editor.linhas[0].nome.setText(" ")
        tela.salvar()
        self.assertIn("nome", tela.aviso.text())
        self.assertEqual(pedidos, [])
        self.assertEqual(Online(self.repo).ajustes().servicos[0].nome, "Barba")

    def test_horario_novo_na_aba_online_muda_a_previa_sem_apagar_o_que_foi_digitado(self) -> None:
        self.criar_link([Servico("s1", "Barba", 15)])
        tela = self.tela()
        tela.editor.linhas[0].nome.setText("Barba completa")
        ajustes = Online(self.repo).ajustes()
        ajustes.semana = [Dia(abre=8 * 60, fecha=12 * 60, almoco=False)] + ajustes.semana[1:]
        Online(self.repo).salvar(ajustes, ativo=True)
        tela.refresh()
        self.assertIn("Segunda: 08:00", tela.editor.linhas[0].previa.text())
        self.assertEqual(tela.editor.linhas[0].nome.text(), "Barba completa")


class JanelaDaAgendaTestCase(Base):
    def janela(self, servidor=None):
        from dumtech.apps.agenda.ui.window import AgendaWindow
        from dumtech.core.app_module import AppContext

        janela = AgendaWindow(AppContext(manifest=modulo_agenda.MANIFEST, paths=self.paths,
                                         servidor=servidor, empresa=self.empresa))
        self.addCleanup(janela.close)
        return janela

    def test_servicos_tem_aba_propria(self) -> None:
        titulos = [tela.title for tela in self.janela().views]
        self.assertEqual(titulos, ["Agenda", "Compromissos", "Serviços", "Online"])

    def test_salvar_servicos_publica_pelo_link(self) -> None:
        Online(self.repo).salvar(AjustesOnline.padrao(), ativo=True)
        servidor = ServidorFalso()
        janela = self.janela(servidor)
        tela = janela.servicos_view
        tela.editor.linhas[0].nome.setText("Barba")
        _escolher(tela.editor.linhas[0].duracao, 15)
        tela.salvar()
        _esperar(lambda: servidor.chamadas and not janela.online_view._publicando)
        funcao, params = servidor.chamadas[-1]
        self.assertEqual(funcao, SALVAR)
        self.assertEqual([(s["nome"], s["duracao"], s["passo"]) for s in params["p_config"]["servicos"]],
                         [("Barba", 15, 15)])
        self.assertIn("Publicado", tela.aviso.text())


if __name__ == "__main__":
    unittest.main()
