"""Testes da conta do cliente e do caminho para a loja.

Nenhum teste acessa a internet: o servidor e substituido por um cliente falso.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dumtech.core.comunicados import ComunicadosService
from dumtech.core.conta import Conta, ContaError, ContaService, email_valido
from dumtech.core.config import Settings
from dumtech.core.licensing import License, ORIGEM_SUPABASE
from dumtech.core import loja
from dumtech.core.loja import LojaService, url_compra
from dumtech.core.supabase import SemConexao, ServicoIndisponivel


def preferencias() -> Settings:
    return Settings(Path(tempfile.mkdtemp(prefix="dumtech_conta_")) / "hub.json")


class ClienteFalso:
    """Servidor de mentira, controlado pelo teste."""

    def __init__(self, resposta=None, excecao: Exception | None = None) -> None:
        self.resposta = resposta if resposta is not None else {"ok": True}
        self.excecao = excecao
        self.chamadas: list[tuple[str, dict]] = []

    def rpc(self, funcao: str, params: dict | None = None):
        self.chamadas.append((funcao, params or {}))
        if self.excecao is not None:
            raise self.excecao
        return self.resposta


class ContaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = preferencias()
        self.cliente = ClienteFalso()
        self.service = ContaService(self.settings, self.cliente)

    def test_email_valido(self) -> None:
        self.assertTrue(email_valido("joao@exemplo.com.br"))
        self.assertFalse(email_valido("joao@exemplo"))
        self.assertFalse(email_valido("joao arroba exemplo.com"))
        self.assertFalse(email_valido(""))

    def test_cadastro_grava_e_avisa_o_servidor(self) -> None:
        conta = self.service.registrar("  Joao da Silva ", " Joao@Exemplo.COM ")

        self.assertTrue(conta.concluido)
        self.assertFalse(conta.pendente)
        self.assertEqual(conta.email, "joao@exemplo.com", "o e-mail e guardado em minusculas")
        self.assertEqual(self.cliente.chamadas[0][0], "dumtech_identificar_cliente")
        self.assertEqual(self.cliente.chamadas[0][1],
                         {"p_nome": "Joao da Silva", "p_email": "joao@exemplo.com"})

    def test_cadastro_sobrevive_a_releitura(self) -> None:
        self.service.registrar("Joao", "joao@exemplo.com")
        outro = Settings(self.settings.file_path)
        self.assertEqual(Conta.carregar(outro).email, "joao@exemplo.com")
        self.assertTrue(Conta.carregar(outro).concluido)

    def test_dados_errados_nem_chegam_no_servidor(self) -> None:
        with self.assertRaises(ContaError):
            self.service.registrar("", "joao@exemplo.com")
        with self.assertRaises(ContaError):
            self.service.registrar("Joao", "nao-e-email")
        self.assertEqual(self.cliente.chamadas, [])
        self.assertFalse(self.service.atual.concluido)

    # ---------------------------------------------------------------- offline
    def test_sem_internet_o_primeiro_acesso_termina_assim_mesmo(self) -> None:
        offline = ContaService(self.settings, ClienteFalso(excecao=SemConexao("sem rede")))
        conta = offline.registrar("Joao", "joao@exemplo.com")

        self.assertTrue(conta.concluido, "o cliente precisa entrar mesmo sem internet")
        self.assertTrue(conta.pendente)
        self.assertFalse(conta.registrada)

    def test_servidor_com_problema_tambem_fica_pendente(self) -> None:
        ruim = ContaService(self.settings, ClienteFalso(excecao=ServicoIndisponivel("nao preparado")))
        self.assertTrue(ruim.registrar("Joao", "joao@exemplo.com").pendente)

    def test_recusa_do_servidor_fica_pendente(self) -> None:
        recusa = ContaService(self.settings, ClienteFalso({"ok": False, "erro": "email_invalido"}))
        self.assertTrue(recusa.registrar("Joao", "joao@exemplo.com").pendente)

    def test_reenvio_do_cadastro_pendente(self) -> None:
        offline = ContaService(self.settings, ClienteFalso(excecao=SemConexao("sem rede")))
        offline.registrar("Joao", "joao@exemplo.com")

        conta = self.service.reenviar("Joao")
        self.assertFalse(conta.pendente)
        self.assertTrue(conta.registrada)
        self.assertEqual(self.cliente.chamadas[0][1]["p_email"], "joao@exemplo.com")

    def test_sem_nada_pendente_nao_fala_com_a_internet(self) -> None:
        self.service.registrar("Joao", "joao@exemplo.com")
        self.cliente.chamadas.clear()

        self.service.reenviar("Joao")
        self.assertEqual(self.cliente.chamadas, [], "nao ha nada pendente para reenviar")

    # ---------------------------------------------------------- um cadastro
    def test_vincular_liga_o_email_a_chave_uma_vez_so(self) -> None:
        self.service.registrar("Maria", "maria@exemplo.com")
        self.cliente.chamadas.clear()
        self.cliente.resposta = {"ok": True, "vinculado": True}

        self.assertTrue(self.service.precisa_vincular("ABCD-EFGH-JKLM-NPQR"))
        self.assertTrue(self.service.vincular("ABCD-EFGH-JKLM-NPQR", "MAQ-1", "Maria"))
        funcao, params = self.cliente.chamadas[0]
        self.assertEqual(funcao, "dumtech_vincular_conta")
        self.assertEqual(params, {"p_chave": "ABCD-EFGH-JKLM-NPQR", "p_maquina": "MAQ-1",
                                  "p_nome": "Maria", "p_email": "maria@exemplo.com"})

        self.service.marcar_vinculo("ABCD-EFGH-JKLM-NPQR")
        self.assertFalse(self.service.precisa_vincular("ABCD-EFGH-JKLM-NPQR"), "ja ligou esta chave")
        self.assertTrue(self.service.precisa_vincular("OUTR-ACHA-VEAA-AAAA"), "chave nova liga de novo")

    def test_vincular_sem_email_ou_sem_chave_nao_viaja(self) -> None:
        self.assertFalse(self.service.precisa_vincular("ABCD-EFGH-JKLM-NPQR"), "sem conta, nada a ligar")
        self.assertFalse(self.service.vincular("ABCD-EFGH-JKLM-NPQR", "MAQ-1", "Maria"))
        self.assertEqual(self.cliente.chamadas, [])

    def test_vincular_tenta_de_novo_so_quando_faz_sentido(self) -> None:
        self.service.registrar("Maria", "maria@exemplo.com")
        casos = [
            ({"ok": True, "vinculado": False}, True),      # o cadastro ja tinha e-mail: encerrado
            ({"ok": False, "erro": "maquina_nao_ativada"}, False),
            ({"ok": False, "erro": "muitas_tentativas"}, False),
            ({"ok": False, "erro": "dados_incompletos"}, True),
        ]
        for resposta, encerrado in casos:
            with self.subTest(resposta=resposta):
                self.cliente.resposta = resposta
                self.assertEqual(self.service.vincular("ABCD-EFGH-JKLM-NPQR", "MAQ-1", "Maria"), encerrado)
        offline = ContaService(self.settings, ClienteFalso(excecao=SemConexao("sem rede")))
        self.assertFalse(offline.vincular("ABCD-EFGH-JKLM-NPQR", "MAQ-1", "Maria"), "sem rede tenta depois")


class LojaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patch = mock.patch.dict(os.environ, {"DUMTECH_URL_LOJA": "https://loja.teste/comprar"})
        patch.start()
        self.addCleanup(patch.stop)

    def licenca(self) -> License:
        return License(
            key="ABCD-EFGH-JKLM-NPQR",
            customer="Joao da Silva",
            entitlements=("estoque", "vendas"),
            machine="MAQ-1111-2222-3333",
            activated_at="2026-09-11T10:00:00+00:00",
            source=ORIGEM_SUPABASE,
        )

    def test_url_com_codigo(self) -> None:
        self.assertEqual(url_compra("abc123"), "https://loja.teste/comprar?t=abc123")

    def test_url_sem_codigo_leva_o_que_o_cliente_ja_tem(self) -> None:
        url = url_compra("", ("vendas", "estoque"))
        self.assertEqual(url, "https://loja.teste/comprar?origem=hub&tem=estoque%2Cvendas")

    def test_cliente_com_licenca_se_identifica_pela_chave(self) -> None:
        cliente = ClienteFalso({"ok": True, "token": "TOKEN-DA-LICENCA"})
        link = LojaService(cliente).link(self.licenca(), "Joao", "joao@exemplo.com")

        self.assertEqual(link, "https://loja.teste/comprar?t=TOKEN-DA-LICENCA")
        funcao, params = cliente.chamadas[0]
        self.assertEqual(funcao, "dumtech_token_compra")
        self.assertEqual(params["p_chave"], "ABCD-EFGH-JKLM-NPQR")
        self.assertEqual(params["p_maquina"], "MAQ-1111-2222-3333")
        self.assertEqual(len(cliente.chamadas), 1, "uma viagem basta")

    def test_visitante_se_identifica_pelo_email(self) -> None:
        cliente = ClienteFalso({"ok": True, "token": "TOKEN-VISITA"})
        link = LojaService(cliente).link(None, "Joao", "joao@exemplo.com")

        self.assertEqual(link, "https://loja.teste/comprar?t=TOKEN-VISITA")
        self.assertEqual(cliente.chamadas[0][1]["p_email"], "joao@exemplo.com")
        self.assertEqual(cliente.chamadas[0][1]["p_chave"], "")

    def test_sem_internet_a_loja_abre_do_mesmo_jeito(self) -> None:
        cliente = ClienteFalso(excecao=SemConexao("sem rede"))
        link = LojaService(cliente).link(self.licenca(), "Joao", "joao@exemplo.com")

        self.assertEqual(link, "https://loja.teste/comprar?origem=hub&tem=estoque%2Cvendas")

    def test_sem_licenca_e_sem_email_nao_ha_o_que_pedir(self) -> None:
        cliente = ClienteFalso()
        link = LojaService(cliente).link(None, "", "")

        self.assertEqual(link, "https://loja.teste/comprar?origem=hub")
        self.assertEqual(cliente.chamadas, [], "sem identificacao, nem vale a viagem")


class LojaLocalTestCase(unittest.TestCase):
    """Sem dominio configurado, o proprio Hub serve a landing page.

    Abrir o index.html por file:// nao serve: o navegador recusa modulos ES
    vindos de arquivo e a pagina abre em branco.
    """

    def setUp(self) -> None:
        # sem loja publicada: nem variavel de ambiente, nem endereco padrao
        for patch in (mock.patch.dict(os.environ, {"DUMTECH_URL_LOJA": ""}),
                      mock.patch.object(loja, "URL_PADRAO", "")):
            patch.start()
            self.addCleanup(patch.stop)

    def test_javascript_sai_com_o_tipo_certo_mesmo_com_registro_errado(self) -> None:
        """Windows com `.js` registrado como text/plain abria a loja em branco."""
        import mimetypes
        import urllib.request

        base = loja.url_base()
        with mock.patch.object(mimetypes, "guess_type", return_value=("text/plain", None)):
            with urllib.request.urlopen(f"{base}/js/app.js", timeout=10) as resposta:
                tipo = resposta.headers.get("Content-Type", "")
        self.assertTrue(tipo.startswith("text/javascript"), tipo)

    def test_a_landing_acompanha_o_programa(self) -> None:
        pasta = loja.pasta_da_landing()
        self.assertIsNotNone(pasta, "a pasta landingpage precisa ser encontrada")
        self.assertTrue((pasta / "index.html").is_file())

    def test_o_hub_serve_a_pagina_de_verdade(self) -> None:
        base = loja.url_base()
        self.assertTrue(base.startswith("http://127.0.0.1:"), base)

        import urllib.request

        with urllib.request.urlopen(f"{base}/index.html", timeout=10) as resposta:
            pagina = resposta.read().decode("utf-8")
        self.assertIn("DumTech", pagina)
        self.assertIn('id="montador"', pagina, "a pagina servida e a landing inteira")

    def test_a_url_de_compra_nasce_do_endereco_local(self) -> None:
        self.assertRegex(url_compra("abc123"), r"^http://127\.0\.0\.1:\d+/\?t=abc123$")

    def test_sem_loja_nenhuma_nao_ha_endereco(self) -> None:
        with mock.patch.object(loja, "pasta_da_landing", return_value=None):
            loja.endereco_local.cache_clear()
            self.addCleanup(loja.endereco_local.cache_clear)
            self.assertEqual(url_compra("abc"), "", "sem loja, o botao nao abre nada")


class ComunicadosTestCase(unittest.TestCase):
    """As ofertas: a tela le o arquivo, a internet so alimenta o arquivo."""

    def setUp(self) -> None:
        self.arquivo = Path(tempfile.mkdtemp(prefix="dumtech_ofertas_")) / "comunicados.json"
        self.resposta = {
            "ok": True,
            "comunicados": [
                {"id": "1", "titulo": "Leve o Vendas", "texto": "Seu balcao mais rapido",
                 "rotulo": "Oferta", "link": ""},
                {"id": "2", "titulo": "Novidade: CRM"},
            ],
        }
        self.cliente = ClienteFalso(self.resposta)
        self.service = ComunicadosService(client=self.cliente, arquivo=self.arquivo)

    def test_sem_arquivo_a_tela_nao_quebra(self) -> None:
        self.assertEqual(self.service.listar(), [])
        self.assertTrue(self.service.precisa_atualizar())

    def test_atualizar_guarda_no_arquivo(self) -> None:
        comunicados = self.service.atualizar("ABCD-EFGH-JKLM-NPQR")

        self.assertEqual([c.titulo for c in comunicados], ["Leve o Vendas", "Novidade: CRM"])
        self.assertEqual(comunicados[0].rotulo, "Oferta")
        self.assertTrue(self.arquivo.exists())
        self.assertEqual(self.cliente.chamadas[0][0], "dumtech_comunicados")
        self.assertEqual(self.cliente.chamadas[0][1], {"p_chave": "ABCD-EFGH-JKLM-NPQR"})

    def test_a_tela_le_o_arquivo_sem_tocar_na_internet(self) -> None:
        self.service.atualizar()
        offline = ComunicadosService(
            client=ClienteFalso(excecao=SemConexao("sem rede")), arquivo=self.arquivo
        )
        self.assertEqual(len(offline.listar()), 2)

    def test_sem_internet_o_que_estava_guardado_continua(self) -> None:
        self.service.atualizar()
        offline = ComunicadosService(
            client=ClienteFalso(excecao=SemConexao("sem rede")), arquivo=self.arquivo
        )
        self.assertEqual(len(offline.atualizar()), 2, "a falha nao pode apagar o que havia")

    def test_so_pergunta_uma_vez_por_dia(self) -> None:
        self.service.atualizar()
        self.assertFalse(self.service.precisa_atualizar())

        dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        dados["buscado_em"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        self.arquivo.write_text(json.dumps(dados), encoding="utf-8")
        self.assertTrue(self.service.precisa_atualizar())

    def test_resposta_estranha_nao_derruba_nem_apaga(self) -> None:
        self.service.atualizar()
        confuso = ComunicadosService(client=ClienteFalso("isso nao e json de oferta"),
                                     arquivo=self.arquivo)
        self.assertEqual(len(confuso.atualizar()), 2)

    def test_arquivo_corrompido_e_tratado_como_vazio(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text("{nao e json", encoding="utf-8")
        self.assertEqual(self.service.listar(), [])

    def test_mostra_no_maximo_tres(self) -> None:
        self.resposta["comunicados"] = [
            {"id": str(i), "titulo": f"Oferta {i}"} for i in range(6)
        ]
        self.assertEqual(len(self.service.atualizar()), 3)

    def test_comunicado_sem_titulo_e_ignorado(self) -> None:
        self.resposta["comunicados"] = [{"id": "1", "titulo": ""}, {"id": "2", "titulo": "Vale"}]
        self.assertEqual([c.titulo for c in self.service.atualizar()], ["Vale"])

    def test_limpar_apaga_o_arquivo(self) -> None:
        self.service.atualizar()
        self.service.limpar()
        self.assertFalse(self.arquivo.exists())
        self.assertEqual(self.service.listar(), [])


if __name__ == "__main__":
    unittest.main()
