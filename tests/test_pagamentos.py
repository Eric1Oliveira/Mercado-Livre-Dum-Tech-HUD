"""Pagamentos protegidos: a chave Pix so vale assinada, e a area so abre com codigo.

O que estes testes protegem e a promessa de seguranca, nao o desenho:
editar o hub.json nao muda para onde vai o dinheiro; codigo e sessao sao
exigidos; sem internet a area nao abre; e o balcao continua vendendo sem chave.
"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dumtech.core import pagamentos
from dumtech.core.config import Settings
from dumtech.core.empresa import Empresa
from dumtech.core.licensing import License
from dumtech.core.pagamentos import (
    FORMAS,
    PagamentosError,
    PagamentosService,
    formas_do_balcao,
    pix_confirmada,
)
from dumtech.core.supabase import FuncaoIndisponivel, SemConexao

from .assinante import COMPUTADOR, b64, licenca_de_teste, pacote, pacote_pix

_app: QApplication | None = None

CHAVE = "7K4M-9QX2-BT5H-3DWZ"
MAQUINA = "AAAA-BBBB"
PIX = "11144477735"


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication([])


def _settings() -> Settings:
    return Settings(Path(tempfile.mkdtemp(prefix="dumtech_pag_")) / "hub.json")


def _licenca(source: str = "supabase") -> License:
    return License(key=CHAVE, customer="Loja", entitlements=("vendas",), machine=MAQUINA,
                   activated_at="", last_check="", source=source)


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


class Cliente:
    """A Edge Function de mentira: uma resposta (ou erro) por rota."""

    def __init__(self, **respostas) -> None:
        self.respostas = respostas
        self.chamadas: list[tuple[str, dict]] = []

    def funcao(self, nome: str, corpo: dict):
        self.chamadas.append((nome, corpo))
        resposta = self.respostas.get(nome.split("/")[-1])
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _entrada(pix: str = PIX) -> dict:
    return {"ok": True, "sessao": "s" * 64, "pix_chave": pix, "assinado": pacote_pix(pix)}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(licenca_de_teste())
        self.settings = _settings()
        self.relogio = Relogio()
        self.licenca = _licenca()

    def servico(self, cliente: Cliente | None = None) -> PagamentosService:
        self.cliente = cliente or Cliente()
        return PagamentosService(self.settings, lambda: self.licenca, self.cliente, self.relogio)

    def liberado(self, **respostas) -> PagamentosService:
        servico = self.servico(Cliente(entrar=_entrada(), **respostas))
        servico.aplicar_entrada(servico.entrar("123456"))
        return servico


# ================================================= a chave que o balcao usa ==
class ChaveAssinadaTestCase(Base):
    def test_sem_nada_nao_ha_chave(self) -> None:
        self.assertEqual(pix_confirmada(self.settings), "")

    def test_chave_assinada_para_este_computador_vale(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX))
        self.assertEqual(pix_confirmada(self.settings), PIX)

    def test_trocar_a_chave_dentro_do_pacote_invalida(self) -> None:
        falso = pacote_pix(PIX)
        conteudo = json.loads(base64.urlsafe_b64decode(falso["licenca"] + "=="))
        conteudo["pix_chave"] = "golpe@banco.com"
        falso["licenca"] = b64(json.dumps(conteudo).encode())
        self.settings.set("pagamentos", "assinado", falso)
        self.assertEqual(pix_confirmada(self.settings), "")

    def test_pacote_copiado_de_outro_computador_nao_vale(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX, computador="b" * 32))
        self.assertEqual(pix_confirmada(self.settings), "")

    def test_licenca_assinada_nao_serve_de_chave_pix(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote(CHAVE, MAQUINA, ["vendas"], pix_chave="golpe@x.com"))
        self.assertEqual(pix_confirmada(self.settings), "")

    def test_chave_escrita_a_mao_no_hub_json_e_ignorada(self) -> None:
        """O ataque mais simples: editar a secao empresa, como era antes."""
        self.settings.set("empresa", "pix_chave", "golpe@banco.com")
        self.settings.set("pagamentos", "pix_chave", "golpe@banco.com")
        self.assertEqual(Empresa.carregar(self.settings).pix_chave, "")
        self.assertFalse(Empresa.carregar(self.settings).tem_pix)

    def test_minha_empresa_nao_grava_chave_pix(self) -> None:
        empresa = Empresa(nome="Loja", pix_chave="golpe@banco.com", formas_ocultas=("Pix",))
        empresa.salvar(self.settings)
        self.assertEqual(self.settings.get("empresa", "pix_chave", ""), "")
        self.assertIsNone(self.settings.get("empresa", "formas_ocultas"))

    def test_a_empresa_carrega_a_chave_assinada(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX))
        self.settings.set("pagamentos", "formas_ocultas", ["Boleto", "inventada"])
        empresa = Empresa.carregar(self.settings)
        self.assertEqual(empresa.pix_chave, PIX)
        self.assertEqual(empresa.formas_ocultas, ("Boleto",))


# ============================================================ o codigo ======
class CodigoTestCase(Base):
    def test_pedir_codigo_manda_a_identidade_e_devolve_o_email_mascarado(self) -> None:
        servico = self.servico(Cliente(codigo={"ok": True, "email": "d**o@loja.com"}))
        self.assertEqual(servico.pedir_codigo(), "d**o@loja.com")
        nome, corpo = self.cliente.chamadas[0]
        self.assertEqual(nome, "pagamentos/codigo")
        self.assertEqual(corpo, {"chave": CHAVE, "maquina": MAQUINA, "computador": COMPUTADOR})

    def test_sem_licenca_do_servidor_nem_tenta(self) -> None:
        for licenca in (_licenca("local"), License.vazia()):
            self.licenca = licenca
            servico = self.servico()
            with self.assertRaises(PagamentosError) as erro:
                servico.pedir_codigo()
            self.assertEqual(erro.exception.codigo, "sem_licenca")
            self.assertEqual(self.cliente.chamadas, [])

    def test_codigo_mal_digitado_nao_vai_ao_servidor(self) -> None:
        servico = self.servico()
        for texto in ("", "12345", "abc", "1234567", "ABCDE-FGHJK"):
            with self.assertRaises(PagamentosError):
                servico.entrar(texto)
        self.assertEqual(self.cliente.chamadas, [])

    def test_recusa_do_servidor_vira_mensagem(self) -> None:
        servico = self.servico(Cliente(entrar={"ok": False, "erro": "codigo_invalido", "mensagem": "Codigo incorreto."}))
        with self.assertRaises(PagamentosError) as erro:
            servico.entrar("123456")
        self.assertEqual(str(erro.exception), "Codigo incorreto.")
        self.assertFalse(servico.liberado)

    def test_sem_internet_e_servico_fora_tem_codigos_proprios(self) -> None:
        servico = self.servico(Cliente(codigo=SemConexao("x"), entrar=FuncaoIndisponivel("503")))
        with self.assertRaises(PagamentosError) as sem:
            servico.pedir_codigo()
        self.assertEqual(sem.exception.codigo, "sem_internet")
        with self.assertRaises(PagamentosError) as fora:
            servico.entrar("123456")
        self.assertEqual(fora.exception.codigo, "indisponivel")

    def test_entrar_libera_e_grava_a_chave_sem_deixar_segredo_no_disco(self) -> None:
        servico = self.liberado()
        self.assertTrue(servico.liberado)
        self.assertEqual(pix_confirmada(self.settings), PIX)
        self.settings.save()
        arquivo = self.settings.file_path.read_text(encoding="utf-8")
        self.assertNotIn("s" * 64, arquivo, "a sessao nunca vai para o disco")

    def test_sem_internet_a_area_nao_abre_e_a_mensagem_explica(self) -> None:
        servico = self.servico(Cliente(codigo=SemConexao("x"), entrar=SemConexao("x")))
        for chamada in (servico.pedir_codigo, lambda: servico.entrar("123456")):
            with self.assertRaises(PagamentosError) as erro:
                chamada()
            self.assertEqual(erro.exception.codigo, "sem_internet")
            self.assertIn("sem internet", str(erro.exception).lower())
        self.assertFalse(servico.liberado)
        self.assertEqual(self.settings.get("pagamentos", "reservas"), None,
                         "nada de codigo guardado neste computador")

    def test_a_sessao_acaba_sozinha(self) -> None:
        servico = self.liberado()
        self.relogio.agora += pagamentos.SESSAO_SEGUNDOS + 1
        self.assertFalse(servico.liberado)
        with self.assertRaises(PagamentosError) as erro:
            servico.salvar_pix("loja@banco.com")
        self.assertEqual(erro.exception.codigo, "sessao_vencida")

    def test_resposta_com_assinatura_falsa_nao_muda_a_chave(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX))
        servico = self.servico()
        falso = pacote_pix("golpe@banco.com", computador="b" * 32)
        self.assertFalse(servico.guardar_assinado(falso))
        with self.assertRaises(PagamentosError):
            servico.aplicar_pix({"ok": True, "assinado": falso})
        self.assertEqual(pix_confirmada(self.settings), PIX)


# ============================================================ trocar ========
class TrocarChaveTestCase(Base):
    def test_trocar_manda_a_chave_normalizada_com_a_sessao(self) -> None:
        servico = self.liberado(salvar={"ok": True, "pix_chave": "loja@banco.com",
                                        "assinado": pacote_pix("loja@banco.com")})
        resposta = servico.salvar_pix("  Loja@Banco.com ")
        nome, corpo = self.cliente.chamadas[-1]
        self.assertEqual(nome, "pagamentos/salvar")
        self.assertEqual(corpo["pix_chave"], "loja@banco.com")
        self.assertEqual(corpo["sessao"], "s" * 64)
        self.assertEqual(servico.aplicar_pix(resposta), "loja@banco.com")

    def test_chave_invalida_nem_sai_do_computador(self) -> None:
        from dumtech.core.pix import PixError

        servico = self.liberado()
        chamadas = len(self.cliente.chamadas)
        with self.assertRaises(PixError):
            servico.salvar_pix("isto nao e chave")
        self.assertEqual(len(self.cliente.chamadas), chamadas)

    def test_conferencia_de_fundo_nunca_levanta(self) -> None:
        for resposta in (SemConexao("x"), FuncaoIndisponivel("404"), {"ok": False, "erro": "nao_autorizado"}, None):
            self.assertIsNone(self.servico(Cliente(atual=resposta)).buscar_atual())
        self.licenca = _licenca("local")
        self.assertIsNone(self.servico(Cliente(atual={"ok": True})).buscar_atual())

    def test_conferencia_de_fundo_corrige_a_chave_local(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix("velha@banco.com"))
        servico = self.servico(Cliente(atual={"ok": True, "assinado": pacote_pix(PIX)}))
        self.assertTrue(servico.guardar_assinado(servico.buscar_atual()["assinado"]))
        self.assertEqual(pix_confirmada(self.settings), PIX)


# ============================================================ formas ========
class FormasTestCase(Base):
    def test_salvar_formas_exige_acesso(self) -> None:
        with self.assertRaises(PagamentosError):
            self.servico().salvar_formas(["Boleto"])

    def test_nao_da_para_esconder_todas(self) -> None:
        servico = self.liberado()
        with self.assertRaises(PagamentosError):
            servico.salvar_formas(list(FORMAS))
        self.assertEqual(servico.salvar_formas(["Prazo", "Boleto"]), ("Boleto", "Prazo"))

    def test_o_balcao_continua_vendendo_sem_internet(self) -> None:
        """A chave ja confirmada vale offline: so mexer nela e que precisa de internet."""
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX))
        self.assertEqual(Empresa.carregar(self.settings).pix_chave, PIX)

    def test_balcao_mostra_so_as_liberadas(self) -> None:
        self.assertEqual(formas_do_balcao(("Boleto", "Prazo")),
                         ["Dinheiro", "Pix", "Cartao de debito", "Cartao de credito"])
        self.assertEqual(formas_do_balcao(FORMAS), ["Dinheiro"])

    def test_receber_respeita_as_formas_e_mostra_o_destino_do_pix(self) -> None:
        from dumtech.apps.vendas.ui.pagamento_dialog import PagamentoDialog

        empresa = Empresa(nome="Loja", cidade="Sao Paulo", pix_chave=PIX, formas_ocultas=("Boleto",))
        dialogo = PagamentoDialog(50.0, "t", empresa=empresa)
        self.addCleanup(dialogo.deleteLater)
        itens = [dialogo.forma.itemText(i) for i in range(dialogo.forma.count())]
        self.assertNotIn("Boleto", itens)
        dialogo.forma.setCurrentText("Pix")
        self.assertIn("CPF final 7735", dialogo.recado_pix.text())


# ============================================================== tela ========
class TelaTestCase(Base):
    def tela(self, servico: PagamentosService):
        from dumtech.hub.views.pagamentos_view import PagamentosView

        tela = PagamentosView(servico)
        self.addCleanup(tela.deleteLater)
        return tela

    def test_abre_trancada_sem_mostrar_a_chave(self) -> None:
        self.settings.set("pagamentos", "assinado", pacote_pix(PIX))
        tela = self.tela(self.servico())
        self.assertEqual(tela.paginas.currentIndex(), 0)
        self.assertNotIn(PIX, tela.pix_atual.text())

    def test_depois_do_codigo_mostra_a_chave(self) -> None:
        servico = self.servico(Cliente(entrar=_entrada()))
        tela = self.tela(servico)
        servico.aplicar_entrada(servico.entrar("123456"))
        tela._mostrar_liberada()
        self.assertEqual(tela.paginas.currentIndex(), 1)
        self.assertIn(PIX, tela.pix_atual.text())
        self.assertIn("Liberado", tela.estado.text())

    def test_trancar_volta_para_a_porta(self) -> None:
        servico = self.liberado()
        tela = self.tela(servico)
        self.assertEqual(tela.paginas.currentIndex(), 1)
        tela.trancar()
        self.assertFalse(servico.liberado)
        self.assertEqual(tela.paginas.currentIndex(), 0)

    def test_tempo_acabou_tranca_a_tela(self) -> None:
        servico = self.liberado()
        tela = self.tela(servico)
        self.relogio.agora += pagamentos.SESSAO_SEGUNDOS + 1
        tela._tique()
        self.assertEqual(tela.paginas.currentIndex(), 0)

    def test_sem_internet_a_tela_explica_e_continua_trancada(self) -> None:
        from PySide6.QtWidgets import QApplication

        servico = self.servico(Cliente(codigo=SemConexao("x")))
        tela = self.tela(servico)
        tela._pedir_codigo()
        QApplication.instance().processEvents()
        for _ in range(50):
            if "internet" in tela.aviso_trancada.text().lower():
                break
            QTest.qWait(20)
        self.assertIn("internet", tela.aviso_trancada.text().lower())
        self.assertEqual(tela.paginas.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
