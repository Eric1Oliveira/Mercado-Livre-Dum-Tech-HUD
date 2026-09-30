"""Licenca assinada: o license.json nao se deixa editar nem copiar.

Nenhum teste acessa a internet. A assinatura de verdade e feita pela Edge
Function (WebCrypto); aqui ha um assinante Ed25519 so para os testes, e um pacote
assinado pelo Node (a mesma WebCrypto da funcao) para provar as duas pontas.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dumtech.core import assinatura, licensing
from dumtech.core.licensing import (
    ORIGEM_SUPABASE,
    License,
    LicenseError,
    LicenseService,
    SemInternet,
    SupabaseLicenseGateway,
    machine_id,
)
from dumtech.core.supabase import FuncaoIndisponivel, SemConexao, SupabaseClient

from .assinante import assinar, b64, publica_de
from .assinante import pacote as _pacote

CHAVE = "7K4M-9QX2-BT5H-3DWZ"
AQUI = "a" * 32   # o computador_id deste computador, nos testes
OUTRO = "b" * 32

# pacote assinado pelo Node (supabase/functions/tests/licenca-assinada.test.mjs)
NODE_PUBLICA = "f48e31aea3d8371c204b1ea47bc3a33de819b59e89bcd65bf71641da8ba7a281"
NODE_PACOTE = {
    "v": 1, "kid": "t1",
    "licenca": "eyJ2IjoxLCJraWQiOiJ0MSIsImNoYXZlIjoiN0s0TS05UVgyLUJUNUgtM0RXWiIsIm1hcXVpbmEiOiJBQjEyLUNEMzQiLCJjb21wdXRhZG9yIjoiYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWEiLCJjbGllbnRlIjoiUGFkYXJpYSBQw6NvIGRlIE91cm8iLCJ0aXBvIjoidml0YWxpY2lhIiwicHJvZHV0b3MiOlsiRVNUT1FVRSIsIlZFTkRBUyJdLCJleHBpcmFfZW0iOm51bGwsIm1heF9jb21wdXRhZG9yZXMiOjMsImVtaXRpZGFfZW0iOiIyMDI2LTA5LTEyVDIzOjU0OjMxLjc5MFoiLCJ2YWxpZGFfYXRlIjoiMjAyNi0xMC0xMlQyMzo1NDozMS43OTBaIn0",
    "assinatura": "s24zDujs0YS8MRaVZEW_Sg1lxsNl4MUqst6FSru-KY-zbBzqOrahvOiyN0r4bkg3G9MhIEmNc3n8bf7P-GHsBA",
}


# o assinante de teste (faz o papel da Edge Function) mora em tests/assinante.py
def pacote(**mudancas) -> dict:
    """Licenca assinada padrao destes testes: Estoque + Vendas, 2 computadores."""
    base = {"cliente": "Padaria Pão de Ouro", "max_computadores": 2, "computador": AQUI}
    base.update(mudancas)
    return _pacote(CHAVE, machine_id(), ["ESTOQUE", "VENDAS"], **base)


def chaves_de_teste():
    return mock.patch.dict(assinatura.CHAVES_PUBLICAS, {"t1": publica_de().hex()})


def neste_computador(valor: str = AQUI):
    return mock.patch.object(assinatura, "computador_id", return_value=valor)


# =============================================================== verificador ==
class VerificadorTestCase(unittest.TestCase):
    def test_assinatura_valida_e_adulteracoes(self) -> None:
        mensagem = "licença de teste".encode()
        sig = assinar(mensagem)
        self.assertTrue(assinatura.verificar_ed25519(publica_de(), mensagem, sig))
        self.assertFalse(assinatura.verificar_ed25519(publica_de(), mensagem + b" ", sig))
        adulterada = bytearray(sig)
        adulterada[10] ^= 1
        self.assertFalse(assinatura.verificar_ed25519(publica_de(), mensagem, bytes(adulterada)))
        outra = publica_de(hashlib.sha256(b"outra").digest())
        self.assertFalse(assinatura.verificar_ed25519(outra, mensagem, sig))

    def test_formatos_invalidos_nao_derrubam(self) -> None:
        self.assertFalse(assinatura.verificar_ed25519(b"curta", b"x", b"\0" * 64))
        self.assertFalse(assinatura.verificar_ed25519(publica_de(), b"x", b"\0" * 10))
        # S >= ordem do grupo: assinatura maleavel e recusada
        sig = assinar(b"x")
        maleavel = sig[:32] + (int.from_bytes(sig[32:], "little") + assinatura._Q).to_bytes(32, "little")
        self.assertFalse(assinatura.verificar_ed25519(publica_de(), b"x", maleavel))

    def test_pacote_assinado_pelo_node_abre_aqui(self) -> None:
        """A funcao assina com WebCrypto; o Hub confere em Python. As duas batem."""
        dados = assinatura.abrir(NODE_PACOTE, {"t1": NODE_PUBLICA})
        self.assertIsNotNone(dados)
        self.assertEqual(dados["cliente"], "Padaria Pão de Ouro")
        self.assertEqual(dados["produtos"], ["ESTOQUE", "VENDAS"])

    def test_abrir_recusa_o_que_nao_confere(self) -> None:
        self.assertIsNone(assinatura.abrir(NODE_PACOTE, {"k1": NODE_PUBLICA}), "kid desconhecido")
        self.assertIsNone(assinatura.abrir(NODE_PACOTE, {"t1": publica_de().hex()}), "chave errada")
        bruto = base64.urlsafe_b64decode(NODE_PACOTE["licenca"] + "==").replace(b"VENDAS", b"AGENDA")
        mexido = dict(NODE_PACOTE, licenca=b64(bruto))
        self.assertNotEqual(mexido["licenca"], NODE_PACOTE["licenca"], "o teste precisa mexer de verdade")
        self.assertIsNone(assinatura.abrir(mexido, {"t1": NODE_PUBLICA}), "conteudo trocado")
        for lixo in (None, "texto", {}, {"kid": "t1", "licenca": "@@@", "assinatura": "!!"}):
            self.assertIsNone(assinatura.abrir(lixo, {"t1": NODE_PUBLICA}))

    def test_prazo_offline(self) -> None:
        agora = datetime(2026, 9, 12, tzinfo=timezone.utc)
        self.assertFalse(assinatura.vencida({"valida_ate": "2026-10-12T00:00:00.000Z"}, agora))
        self.assertTrue(assinatura.vencida({"valida_ate": "2026-09-01T00:00:00Z"}, agora))
        self.assertTrue(assinatura.vencida({}, agora), "sem prazo = vencida (nao confia)")

    def test_computador_id_estavel(self) -> None:
        primeiro = assinatura.computador_id()
        self.assertEqual(primeiro, assinatura.computador_id())
        self.assertRegex(primeiro, r"^[0-9a-f]{32}$")

    def test_a_chave_publica_do_hub_e_valida(self) -> None:
        for kid, publica in assinatura.CHAVES_PUBLICAS.items():
            with self.subTest(kid=kid):
                self.assertIsNotNone(assinatura._descomprimir(bytes.fromhex(publica)))


# ============================================================ license.json ==
class ArquivoAssinadoTestCase(unittest.TestCase):
    """O que acontece quando alguem mexe no license.json."""

    def setUp(self) -> None:
        for patch in (mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}),
                      chaves_de_teste(), neste_computador()):
            patch.start()
            self.addCleanup(patch.stop)
        self.arquivo = Path(tempfile.mkdtemp(prefix="dumtech_ass_")) / "license.json"

    def gravar(self, **campos) -> None:
        agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        base = License(
            key=CHAVE, customer="Padaria Pão de Ouro", entitlements=("estoque", "vendas"),
            machine=machine_id(), activated_at=agora, last_check=agora, source=ORIGEM_SUPABASE,
            max_machines=2, assinado=pacote(),
        ).to_dict()
        base.update(campos)
        self.arquivo.write_text(json.dumps(base), encoding="utf-8")

    def carregar(self) -> License:
        return LicenseService(self.arquivo, gateway=mock.Mock()).current

    def test_licenca_assinada_abre_normalmente(self) -> None:
        self.gravar()
        licenca = self.carregar()
        self.assertTrue(licenca.allows("estoque"))
        self.assertTrue(licenca.allows("vendas"))
        self.assertEqual(licenca.bloqueio, "")

    def test_acrescentar_modulo_no_arquivo_nao_libera(self) -> None:
        self.gravar(entitlements=["estoque", "vendas", "financeiro", "agenda"])
        licenca = self.carregar()
        self.assertTrue(licenca.allows("vendas"))
        self.assertFalse(licenca.allows("financeiro"))
        self.assertFalse(licenca.allows("agenda"))

    def test_esticar_o_prazo_no_arquivo_nao_adianta(self) -> None:
        self.gravar(assinado=pacote(tipo="teste", expira_em="2020-01-01"), expires_at=None)
        licenca = self.carregar()
        self.assertEqual(licenca.expires_at, "2020-01-01")
        self.assertFalse(licenca.allows("estoque"))

    def test_trocar_o_conteudo_assinado_invalida_tudo(self) -> None:
        falso = pacote()
        conteudo = json.loads(base64.urlsafe_b64decode(falso["licenca"] + "=="))
        conteudo["produtos"].append("FINANCEIRO")
        falso["licenca"] = b64(json.dumps(conteudo).encode())
        self.gravar(entitlements=["estoque", "vendas", "financeiro"], assinado=falso)
        licenca = self.carregar()
        self.assertFalse(licenca.ativa)
        self.assertFalse(licenca.allows("estoque"))

    def test_arquivo_copiado_para_outro_computador_nao_abre(self) -> None:
        self.gravar()
        with neste_computador(OUTRO):
            licenca = self.carregar()
        self.assertFalse(licenca.ativa)
        self.assertEqual(licenca.entitlements, ())

    def test_assinatura_de_outra_chave_nao_serve(self) -> None:
        self.gravar(key="AAAA-BBBB-CCCC-DDDD")
        self.assertFalse(self.carregar().ativa)

    def test_offline_demais_pede_internet_e_confere_na_hora(self) -> None:
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.gravar(assinado=pacote(valida_ate=ontem))
        servico = LicenseService(self.arquivo, gateway=mock.Mock())
        self.assertFalse(servico.allows("estoque"))
        self.assertEqual(servico.current.bloqueio, "conferencia_vencida")
        self.assertTrue(servico.precisa_conferir(), "nao espera o intervalo: so a conferencia destrava")

    def test_origem_inventada_no_arquivo_nao_pula_a_assinatura(self) -> None:
        for origem in ("xyz", "nenhuma", ""):
            self.gravar(source=origem, assinado={})
            licenca = self.carregar()
            self.assertFalse(licenca.ativa, origem)
            self.assertFalse(licenca.allows("estoque"), origem)

    def test_licenca_local_no_cliente_nao_abre(self) -> None:
        self.gravar(source="local", assinado={})
        self.assertFalse(self.carregar().allows("estoque"))

    def test_outro_documento_assinado_nao_vira_licenca(self) -> None:
        self.gravar(assinado=pacote(uso="pagamentos"))
        self.assertFalse(self.carregar().ativa)

    def test_bloqueio_do_servidor_continua_valendo(self) -> None:
        """Assinatura antiga com modulos + bloqueio gravado depois = continua bloqueada."""
        self.gravar(entitlements=[], extras={"bloqueio": "inativa", "mensagem": "suspensa"})
        licenca = self.carregar()
        self.assertEqual(licenca.entitlements, ())
        self.assertEqual(licenca.bloqueio, "inativa")

    def test_sem_assinatura_nao_abre(self) -> None:
        self.gravar(assinado={})
        # ligada (o padrao desde 13/09/2026): sem assinatura nao abre, e confere na hora
        servico = LicenseService(self.arquivo, gateway=mock.Mock())
        self.assertTrue(licensing.ASSINATURA_OBRIGATORIA, "a assinatura precisa estar obrigatoria no Hub distribuido")
        self.assertFalse(servico.allows("estoque"))
        self.assertEqual(servico.current.bloqueio, "sem_assinatura")
        self.assertTrue(servico.precisa_conferir())
        # desligada, o arquivo sem assinatura ainda abriria (o jeito antigo)
        with mock.patch.object(licensing, "ASSINATURA_OBRIGATORIA", False):
            self.assertTrue(self.carregar().allows("estoque"))


# ================================================================ gateway ===
class ClienteComFuncao:
    """Servidor de mentira que tem RPC e Edge Function."""

    def __init__(self, funcao=None, rpc=None) -> None:
        self.resposta_funcao = funcao
        self.resposta_rpc = rpc or {"ok": True, "chave": CHAVE, "cliente": "X", "produtos": ["ESTOQUE"]}
        self.chamadas: list[str] = []

    def funcao(self, nome, corpo):
        self.chamadas.append(nome)
        if isinstance(self.resposta_funcao, Exception):
            raise self.resposta_funcao
        return self.resposta_funcao

    def rpc(self, nome, params):
        self.chamadas.append(nome)
        return self.resposta_rpc


class GatewayAssinadoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patch = neste_computador()
        patch.start()
        self.addCleanup(patch.stop)

    def test_verificar_traz_a_licenca_assinada(self) -> None:
        cliente = ClienteComFuncao(funcao={
            "ok": True, "chave": CHAVE, "cliente": "X", "produtos": ["ESTOQUE", "VENDAS"],
            "assinado": pacote(),
        })
        licenca = SupabaseLicenseGateway(cliente).verify(CHAVE, machine_id())
        self.assertEqual(cliente.chamadas, ["licenca-assinada"], "com a funcao, nada de RPC")
        self.assertEqual(licenca.assinado["kid"], "t1")
        self.assertEqual(licenca.entitlements, ("estoque", "vendas"))

    def test_funcao_nao_publicada_cai_na_verificacao_antiga(self) -> None:
        cliente = ClienteComFuncao(funcao=FuncaoIndisponivel("404"))
        licenca = SupabaseLicenseGateway(cliente).verify(CHAVE, machine_id())
        self.assertEqual(cliente.chamadas, ["licenca-assinada", "dumtech_verificar_licenca"])
        self.assertEqual(licenca.assinado, {})
        self.assertEqual(licenca.entitlements, ("estoque",))

    def test_sem_internet_nao_tenta_de_novo(self) -> None:
        cliente = ClienteComFuncao(funcao=SemConexao("offline"))
        with self.assertRaises(SemInternet):
            SupabaseLicenseGateway(cliente).verify(CHAVE, machine_id())
        self.assertEqual(cliente.chamadas, ["licenca-assinada"])

    def test_recusa_da_funcao_e_recusa_de_verdade(self) -> None:
        cliente = ClienteComFuncao(funcao={"ok": False, "erro": "inativa", "mensagem": "Suspensa."})
        with self.assertRaises(LicenseError) as caso:
            SupabaseLicenseGateway(cliente).verify(CHAVE, machine_id())
        self.assertEqual(caso.exception.codigo, "inativa")

    def test_ativar_vale_mesmo_sem_a_funcao(self) -> None:
        cliente = ClienteComFuncao(funcao=FuncaoIndisponivel("404"))
        licenca = SupabaseLicenseGateway(cliente).fetch(CHAVE, machine_id())
        self.assertEqual(cliente.chamadas[0], "dumtech_ativar_licenca")
        self.assertEqual(licenca.entitlements, ("estoque",))
        self.assertEqual(licenca.assinado, {})

    def test_ativacao_assinada_sobrevive_ao_arquivo(self) -> None:
        cliente = ClienteComFuncao(funcao={"ok": True, "chave": CHAVE, "cliente": "X",
                                           "produtos": ["ESTOQUE", "VENDAS"], "assinado": pacote()})
        arquivo = Path(tempfile.mkdtemp(prefix="dumtech_ass_")) / "license.json"
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "0"}), chaves_de_teste():
            LicenseService(arquivo, SupabaseLicenseGateway(cliente)).activate(CHAVE)
            recarregada = LicenseService(arquivo, gateway=mock.Mock()).current
        self.assertTrue(recarregada.allows("estoque"))
        self.assertTrue(recarregada.assinado)


class ProgramaInstaladoTestCase(unittest.TestCase):
    """No .exe as variaveis de desenvolvimento nao valem."""

    def test_modo_local_desligado_no_exe(self) -> None:
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "1"}),              mock.patch.object(licensing.sys, "frozen", True, create=True):
            self.assertFalse(licensing.modo_local_ligado())
        with mock.patch.dict(os.environ, {"DUMTECH_LICENCA_LOCAL": "1"}):
            self.assertTrue(licensing.modo_local_ligado())

    def test_servidor_nao_troca_por_variavel_no_exe(self) -> None:
        from dumtech.core import supabase

        falso = {"DUMTECH_SUPABASE_URL": "https://golpe.example/rest/v1", "DUMTECH_SUPABASE_KEY": "x"}
        with mock.patch.dict(os.environ, falso),              mock.patch.object(supabase.sys, "frozen", True, create=True):
            cliente = SupabaseClient()
        self.assertEqual(cliente.url, supabase.URL_PADRAO)
        self.assertEqual(cliente.anon_key, supabase.CHAVE_PADRAO)


class ClienteHttpFuncaoTestCase(unittest.TestCase):
    """SupabaseClient.funcao: endereco certo e erros traduzidos."""

    def test_endereco_da_funcao(self) -> None:
        cliente = SupabaseClient(url="https://abc.supabase.co/rest/v1", anon_key="k")
        resposta = mock.MagicMock()
        resposta.__enter__.return_value.read.return_value = b'{"ok": true}'
        with mock.patch("urllib.request.urlopen", return_value=resposta) as abrir:
            self.assertEqual(cliente.funcao("licenca-assinada", {"a": 1}), {"ok": True})
        self.assertEqual(abrir.call_args[0][0].full_url, "https://abc.supabase.co/functions/v1/licenca-assinada")

    def test_qualquer_erro_http_da_funcao_manda_para_o_caminho_antigo(self) -> None:
        cliente = SupabaseClient(url="https://abc.supabase.co/rest/v1", anon_key="k")
        for codigo in (401, 404, 500, 503):
            erro = urllib.error.HTTPError("u", codigo, "x", {}, io.BytesIO(b"{}"))
            with self.subTest(codigo=codigo), mock.patch("urllib.request.urlopen", side_effect=erro):
                with self.assertRaises(FuncaoIndisponivel):
                    cliente.funcao("licenca-assinada", {})

    def test_sem_rede_continua_sendo_sem_rede(self) -> None:
        cliente = SupabaseClient(url="https://abc.supabase.co/rest/v1", anon_key="k")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns")):
            with self.assertRaises(SemConexao):
                cliente.funcao("licenca-assinada", {})


if __name__ == "__main__":
    unittest.main()
