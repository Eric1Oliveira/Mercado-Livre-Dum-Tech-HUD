"""Contas do Hub: o que estes testes protegem e a promessa, nao o desenho.

Loja sem conta nao sente nada; login funciona sem internet; editar arquivo nao
transforma funcionario em ADM; apagar o pacote nao libera o Hub; e o funcionario
ve so o que foi marcado.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from dumtech.core import acesso as nucleo
from dumtech.core.acesso import AcessoError, AcessoService, Usuario, forca_da_senha, validar_login, validar_senha
from dumtech.core.avisos import TIPOS
from dumtech.core.licensing import License, LicenseService
from dumtech.core.registry import AppRegistry
from dumtech.core.supabase import FuncaoIndisponivel, SemConexao

from .assinante import COMPUTADOR, licenca_de_teste, pacote, pacote_acesso, pacote_lembranca

CHAVE = "7K4M-9QX2-BT5H-3DWZ"
MAQUINA = "AAAA-BBBB"
ADM = "11111111-1111-1111-1111-111111111111"
MARIA = "22222222-2222-2222-2222-222222222222"


def conta(id_=ADM, login="dona", papel="adm", **extras) -> dict:
    return {"id": id_, "login": login, "nome": login.title(), "papel": papel, "modulos": [], "avisos": [],
            "senha_versao": 1, "trocar_senha": False, "ativo": True, "tem_email": True,
            "email_confirmado": True, **extras}


def maria(**extras) -> dict:
    campos = {"modulos": ["vendas"], "avisos": ["estoque_baixo"], "tem_email": False, **extras}
    return conta(MARIA, "maria", "funcionario", **campos)


class ServidorFalso:
    """Faz o papel da Edge Function `acesso`."""

    def __init__(self) -> None:
        self.respostas: dict = {}
        self.chamadas: list = []
        self.erro: Exception | None = None

    def funcao(self, nome, corpo):
        self.chamadas.append((nome, corpo))
        if self.erro is not None:
            raise self.erro
        resposta = self.respostas[nome.split("/")[-1]]
        return resposta(corpo) if callable(resposta) else resposta

    def rotas(self) -> list:
        return [nome.split("/")[-1] for nome, _ in self.chamadas]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.contexto = licenca_de_teste()
        self.contexto.__enter__()
        self.addCleanup(self.contexto.__exit__, None, None, None)
        rapido = mock.patch.object(nucleo, "ITERACOES_LOCAIS", 1000)
        rapido.start()
        self.addCleanup(rapido.stop)

        pasta = Path(tempfile.mkdtemp(prefix="dumtech_acesso_"))
        self.arquivo = pasta / "acesso.json"
        self.licencas = LicenseService(file_path=pasta / "license.json", gateway=mock.Mock())
        self.servidor = ServidorFalso()
        self.servico = AcessoService(self.licencas, self.arquivo, client=self.servidor)

    def licenca(self, usuarios=(), *, contas=None, exigir_conta=False, documento=True) -> None:
        contas = bool(usuarios) if contas is None else contas
        self.licencas.save(License(
            key=CHAVE, customer="Loja", entitlements=("agenda", "estoque", "vendas"), machine=MAQUINA,
            activated_at="2026-11-01T10:00:00+00:00", source="supabase",
            assinado=pacote(CHAVE, MAQUINA, ("agenda", "estoque", "vendas"), contas=contas),
            acesso=pacote_acesso(usuarios, exigir_conta=exigir_conta) if documento else {},
        ))
        self.licencas.reload()

    def resposta_entrar(self, usuario=None, usuarios=None, sessao="segredo", lembrar=False) -> dict:
        usuario = usuario or conta()
        resposta = {"ok": True, "sessao": sessao, "usuario": usuario,
                    "acesso_assinado": pacote_acesso(usuarios or [usuario])}
        if lembrar:
            resposta["lembranca"] = pacote_lembranca(usuario["id"], usuario["senha_versao"])
        return resposta

    def entrar(self, login="dona", senha="cavalo-azul", lembrar=True, usuario=None, usuarios=None):
        usuario = usuario or conta()
        self.servidor.respostas["entrar"] = self.resposta_entrar(usuario, usuarios, lembrar=lembrar)
        return self.servico.aplicar(self.servico.entrar(login, senha, lembrar))

    def local(self) -> dict:
        return json.loads(self.arquivo.read_text(encoding="utf-8"))

    def novo_servico(self) -> AcessoService:
        """O Hub fechou e abriu de novo."""
        self.licencas.reload()
        return AcessoService(self.licencas, self.arquivo, client=self.servidor)


class LojaSemConta(Base):
    def test_loja_sem_conta_abre_como_sempre(self) -> None:
        self.licenca()
        self.assertFalse(self.servico.ha_contas)
        self.assertFalse(self.servico.precisa_login())
        self.assertTrue(self.servico.e_adm)
        self.assertTrue(self.servico.permite_modulo("financeiro"))
        self.assertTrue(self.servico.permite_aviso("conta_vencida"))

    def test_licenca_local_de_desenvolvimento_nao_pede_nada(self) -> None:
        self.licencas.save(License(key="LOCAL", customer="", entitlements=("vendas",), machine=MAQUINA,
                                   activated_at="", source="local"))
        self.assertFalse(self.servico.precisa_login())
        self.assertFalse(self.servico.falta_documento())

    def test_hub_aberto_nao_perde_as_abas_quando_a_conta_nasce_em_outro_computador(self) -> None:
        self.licenca()
        self.servico.nova_abertura()
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria()]))
        self.assertTrue(self.servico.ha_contas)
        self.assertFalse(self.servico.precisa_login(), "pede na proxima abertura, nao agora")
        self.assertTrue(self.servico.permite_modulo("vendas"))
        self.servico.nova_abertura()
        self.assertTrue(self.servico.precisa_login(), "abriu de novo: agora pede")

    def test_licenca_antiga_sem_documento_pede_conferencia(self) -> None:
        self.licenca(documento=False)
        self.assertTrue(self.servico.falta_documento())
        self.assertFalse(self.servico.precisa_login(), "sem saber, nao trava a loja")


class ComContas(Base):
    def test_com_contas_ninguem_entra_sem_login(self) -> None:
        self.licenca([conta(), maria()])
        self.assertTrue(self.servico.precisa_login())
        self.assertFalse(self.servico.e_adm)
        self.assertFalse(self.servico.permite_modulo("vendas"))
        self.assertFalse(self.servico.permite_aviso("estoque_baixo"))

    def test_apagar_o_pacote_nao_libera_o_hub(self) -> None:
        self.licenca(contas=True, documento=False)
        self.assertTrue(self.servico.ha_contas, "a licenca assinada diz que ha contas")
        self.assertTrue(self.servico.precisa_login())

    def test_arquivo_nao_diz_que_nao_ha_contas(self) -> None:
        self.licenca([conta()])
        bruto = json.loads(self.licencas.file_path.read_text(encoding="utf-8"))
        bruto["tem_contas"] = False
        bruto["acesso"] = {}
        self.licencas.file_path.write_text(json.dumps(bruto), encoding="utf-8")
        self.assertTrue(self.novo_servico().precisa_login())

    def test_pacote_de_outro_computador_nao_vale(self) -> None:
        self.licenca([conta()])
        self.licencas.guardar_acesso(pacote_acesso([], computador="b" * 32))
        self.assertEqual(self.servico.documento(), None)
        self.assertTrue(self.servico.precisa_login(), "a licenca assinada continua dizendo que ha contas")

    def test_pacote_adulterado_nao_vale(self) -> None:
        self.licenca([conta()])
        pacote_ruim = dict(pacote_acesso([conta()]))
        pacote_ruim["licenca"] = pacote_acesso([maria()])["licenca"]
        self.licencas.guardar_acesso(pacote_ruim)
        self.assertEqual(self.servico.documento(), None)

    def test_outro_documento_assinado_nao_vira_contas(self) -> None:
        self.licenca([conta()])
        self.licencas.guardar_acesso(pacote_acesso([conta()], uso="pagamentos"))
        self.assertEqual(self.servico.documento(), None)


class Entrar(Base):
    def test_entrar_online_abre_gestao_e_guarda_verificador(self) -> None:
        self.licenca([conta()])
        usuario = self.entrar()
        self.assertIsInstance(usuario, Usuario)
        self.assertTrue(self.servico.e_adm)
        self.assertTrue(self.servico.gestao_aberta)
        local = self.local()
        self.assertIn(ADM, local["locais"])
        bruto = self.arquivo.read_text(encoding="utf-8")
        self.assertNotIn("cavalo-azul", bruto)
        self.assertNotIn("segredo", bruto, "sessao de gestao so na memoria")
        self.assertEqual(local["recentes"][0], ADM)

    def test_senha_errada_no_servidor(self) -> None:
        self.licenca([conta()])
        self.servidor.respostas["entrar"] = {"ok": False, "erro": "credenciais", "mensagem": "Login ou senha incorretos."}
        with self.assertRaises(AcessoError) as erro:
            self.servico.entrar("dona", "errada", True)
        self.assertEqual(erro.exception.codigo, "credenciais")

    def test_offline_entra_com_a_senha_certa(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servidor.erro = SemConexao("sem rede")
        servico = self.novo_servico()
        servico.sair(esquecer=True)
        usuario = servico.aplicar(servico.entrar("dona", "cavalo-azul", False))
        self.assertEqual(usuario.id, ADM)
        self.assertFalse(servico.gestao_aberta, "offline nao abre gestao")

    def test_offline_senha_errada_nao_entra(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servidor.erro = SemConexao("sem rede")
        with self.assertRaises(AcessoError) as erro:
            self.servico.entrar("dona", "outra-senha", False)
        self.assertEqual(erro.exception.codigo, "credenciais")

    def test_servidor_fora_do_ar_tambem_entra_offline(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servidor.erro = FuncaoIndisponivel("503")
        self.assertEqual(self.servico.aplicar(self.servico.entrar("dona", "cavalo-azul", False)).id, ADM)

    def test_primeiro_login_neste_computador_precisa_de_internet(self) -> None:
        self.licenca([conta(), maria()])
        self.servidor.erro = SemConexao("sem rede")
        with self.assertRaises(AcessoError) as erro:
            self.servico.entrar("maria", "qualquer-uma", False)
        self.assertEqual(erro.exception.codigo, "primeiro_acesso_online")

    def test_senha_trocada_em_outro_computador_invalida_o_offline(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.licencas.guardar_acesso(pacote_acesso([conta(senha_versao=2)]))
        self.servidor.erro = SemConexao("sem rede")
        with self.assertRaises(AcessoError) as erro:
            self.servico.entrar("dona", "cavalo-azul", False)
        self.assertEqual(erro.exception.codigo, "senha_mudou")

    def test_conta_bloqueada_nao_entra_offline(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.licencas.guardar_acesso(pacote_acesso([conta(ativo=False)]))
        self.servidor.erro = SemConexao("sem rede")
        with self.assertRaises(AcessoError) as erro:
            self.servico.entrar("dona", "cavalo-azul", False)
        self.assertEqual(erro.exception.codigo, "conta_bloqueada")

    def test_resposta_sem_assinatura_que_confere_nao_entra(self) -> None:
        self.licenca([maria()])
        falsa = self.resposta_entrar()
        falsa["acesso_assinado"] = {"v": 1, "kid": "t1", "licenca": "x", "assinatura": "y"}
        self.servidor.respostas["entrar"] = falsa
        with self.assertRaises(AcessoError) as erro:
            self.servico.aplicar(self.servico.entrar("dona", "cavalo-azul", False))
        self.assertEqual(erro.exception.codigo, "assinatura")
        self.assertIsNone(self.servico.usuario)


class Lembrar(Base):
    def test_lembrado_abre_direto(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        servico = self.novo_servico()
        self.assertTrue(servico.precisa_login())
        self.assertEqual(servico.abrir_lembrado().id, ADM)
        self.assertFalse(servico.precisa_login())
        self.assertFalse(servico.gestao_aberta, "lembrado nao tem sessao de gestao")

    def test_sem_lembrar_pede_senha_na_proxima(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=False)
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_editar_o_json_nao_vira_adm(self) -> None:
        self.licenca([conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()], lembrar=True)
        bruto = self.local()
        bruto["lembrado"] = ADM
        self.arquivo.write_text(json.dumps(bruto), encoding="utf-8")
        self.assertIsNone(self.novo_servico().abrir_lembrado(), "sem lembranca da ADM, nao abre como ADM")

    def test_trocar_o_id_dentro_do_local_nao_vira_adm(self) -> None:
        self.licenca([conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()], lembrar=True)
        bruto = self.local()
        bruto["lembrado"] = ADM
        bruto["locais"][ADM] = bruto["locais"][MARIA]   # a lembranca e da Maria, assinada
        self.arquivo.write_text(json.dumps(bruto), encoding="utf-8")
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_lembranca_de_outro_computador_nao_vale(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        bruto = self.local()
        bruto["locais"][ADM]["lembranca"] = pacote_lembranca(ADM, computador="b" * 32)
        self.arquivo.write_text(json.dumps(bruto), encoding="utf-8")
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_senha_trocada_derruba_a_lembranca(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        self.licencas.guardar_acesso(pacote_acesso([conta(senha_versao=2)]))
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_quem_precisa_trocar_a_senha_nao_entra_direto(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        self.licencas.guardar_acesso(pacote_acesso([conta(trocar_senha=True)]))
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_trocar_de_usuario_nao_devolve_a_conta_sem_senha(self) -> None:
        """Quem trocou passou o computador: reabrir o Hub nao pode virar a conta dele."""
        self.licenca([conta()])
        self.entrar(lembrar=True)
        self.servico.sair(esquecer=False)
        self.assertIsNone(self.servico.usuario)
        self.assertIsNone(self.novo_servico().abrir_lembrado())
        self.assertIn("lembranca", self.local()["locais"][ADM], "volta a ser lembrado ao entrar de novo")

    def test_sair_apaga_a_lembranca_mas_nao_o_login_offline(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        self.servico.sair(esquecer=True)
        self.assertIsNone(self.novo_servico().abrir_lembrado())
        self.assertNotIn("lembranca", self.local()["locais"][ADM])
        self.assertIn("verificador", self.local()["locais"][ADM])

    def test_entrar_sem_lembrar_nao_deixa_outro_lembrado(self) -> None:
        self.licenca([conta(), maria()])
        self.entrar(lembrar=True, usuarios=[conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()], lembrar=False)
        self.assertIsNone(self.novo_servico().abrir_lembrado())

    def test_recentes_so_quem_ainda_existe(self) -> None:
        self.licenca([conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()])
        self.entrar(usuarios=[conta(), maria()])
        self.assertEqual([u.login for u in self.servico.recentes()], ["dona", "maria"])
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(ativo=False)]))
        self.assertEqual([u.login for u in self.servico.recentes()], ["dona"])


class SenhaProvisoria(Base):
    def test_senha_provisoria_nao_abre_nada_ate_criar_a_propria(self) -> None:
        provisoria = conta(trocar_senha=True)
        self.licenca([provisoria])
        self.entrar(usuario=provisoria, usuarios=[provisoria], lembrar=False)
        self.assertIsNotNone(self.servico.usuario, "a tela precisa saber quem esta trocando")
        self.assertTrue(self.servico.precisa_login(), "mas ainda nao entrou")
        self.assertFalse(self.servico.e_adm)
        self.assertFalse(self.servico.permite_modulo("vendas"))


class ComputadorFora(Base):
    def test_vaga_solta_reconhece_o_bloqueio(self) -> None:
        self.licenca([conta()])
        self.assertFalse(self.servico.computador_fora)
        self.licencas._bloquear("Ative de novo", "maquina_nao_ativada")
        self.assertTrue(self.servico.computador_fora)

    def test_licenca_vencida_nao_e_computador_fora(self) -> None:
        self.licenca([conta()])
        self.licencas._bloquear("Venceu", "expirada")
        self.assertFalse(self.servico.computador_fora, "ai a senha ainda resolve")


class Corrida(Base):
    def test_conferencia_no_ar_nao_apaga_o_pacote_que_a_tela_gravou(self) -> None:
        """A pessoa troca a senha com a conferencia de hora em hora rodando."""
        self.licenca([conta()])
        velho = pacote_acesso([conta()])
        novo = pacote_acesso([conta(senha_versao=2)])

        def conferencia(*_args):
            self.licencas.guardar_acesso(novo)   # a tela grava enquanto a rede responde
            return replace(self.licencas.current, acesso=velho)

        self.licencas.gateway.verify.side_effect = conferencia
        self.assertEqual(self.licencas.verify().acesso, novo)

    def test_sem_gravar_nada_vale_o_que_chegou(self) -> None:
        self.licenca([conta()])
        novo = pacote_acesso([conta(), maria()])
        self.licencas.gateway.verify.return_value = replace(self.licencas.current, acesso=novo)
        self.assertEqual(self.licencas.verify().acesso, novo)


class Permissoes(Base):
    def test_funcionario_ve_so_o_marcado(self) -> None:
        self.licenca([conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()])
        self.assertFalse(self.servico.e_adm)
        self.assertTrue(self.servico.permite_modulo("vendas"))
        self.assertFalse(self.servico.permite_modulo("estoque"))
        self.assertTrue(self.servico.permite_aviso("estoque_baixo"))
        self.assertFalse(self.servico.permite_aviso("conta_vencida"))

    def test_adm_ve_tudo_mesmo_modulo_novo(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.assertTrue(self.servico.permite_modulo("qualquer_coisa"))
        self.assertTrue(self.servico.permite_aviso("qualquer_coisa"))

    def test_visiveis_e_o_que_a_pessoa_ve_available_o_que_a_licenca_libera(self) -> None:
        self.licenca([conta(), maria()])
        registro = AppRegistry(self.licencas)
        registro.usar_acesso(self.servico)
        self.assertEqual(registro.visiveis(), [], "ninguem logado")
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()])
        self.assertEqual([e.app_id for e in registro.visiveis()], ["vendas"])
        self.assertEqual(sorted(e.app_id for e in registro.available()), ["agenda", "estoque", "vendas"],
                         "celular e sincronias continuam vendo a loja inteira")

    def test_visiveis_sem_acesso_ligado_e_a_licenca(self) -> None:
        self.licenca()
        registro = AppRegistry(self.licencas)
        self.assertEqual(registro.visiveis(), registro.available())


class Gestao(Base):
    def test_gestao_vence_sozinha(self) -> None:
        self.licenca([conta()])
        relogio = mock.Mock(return_value=100.0)
        self.servico._relogio = relogio
        self.entrar()
        self.assertEqual(self.servico.sessao, "segredo")
        relogio.return_value = 100.0 + nucleo.SESSAO_SEGUNDOS + 1
        self.assertFalse(self.servico.gestao_aberta)
        self.assertEqual(self.servico.sessao, "")

    def test_sem_gestao_nao_vai_a_rede(self) -> None:
        self.licenca([conta()])
        with self.assertRaises(AcessoError) as erro:
            self.servico.listar_usuarios()
        self.assertEqual(erro.exception.codigo, "sessao_vencida")
        self.assertEqual(self.servidor.chamadas, [])

    def test_trancar_apaga_o_segredo(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servico.trancar_gestao()
        self.assertEqual(self.servico.sessao, "")
        self.assertIsNotNone(self.servico.usuario, "trancar a gestao nao tira a pessoa do computador")

    def test_reabrir_gestao_exige_internet(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servico.trancar_gestao()
        self.servidor.erro = SemConexao("sem rede")
        with self.assertRaises(AcessoError) as erro:
            self.servico.reabrir_gestao("cavalo-azul")
        self.assertEqual(erro.exception.codigo, "sem_internet")

    def test_reabrir_gestao_nao_mexe_na_lembranca(self) -> None:
        self.licenca([conta()])
        self.entrar(lembrar=True)
        self.servico.trancar_gestao()
        self.servidor.erro = None
        self.servidor.respostas["entrar"] = self.resposta_entrar()
        self.servico.aplicar(self.servico.reabrir_gestao("cavalo-azul"))
        self.assertEqual(self.servico.sessao, "segredo")
        self.assertEqual(self.novo_servico().abrir_lembrado().id, ADM)

    def test_salvar_usuario_manda_sessao_e_guarda_o_documento_novo(self) -> None:
        self.licenca([conta()])
        self.entrar()
        self.servidor.respostas["salvar-usuario"] = {
            "ok": True, "usuario": maria(), "acesso_assinado": pacote_acesso([conta(), maria()])}
        resposta = self.servico.salvar_usuario({"nome": "Maria", "login": "maria", "papel": "funcionario"}, "senha-boa-1")
        self.servico.guardar_documento(resposta["acesso_assinado"])
        nome, corpo = self.servidor.chamadas[-1]
        self.assertEqual(corpo["sessao"], "segredo")
        self.assertEqual(corpo["senha"], "senha-boa-1")
        self.assertEqual(corpo["computador"], COMPUTADOR)
        self.assertEqual(sorted(u.login for u in self.servico.usuarios()), ["dona", "maria"])


class Reconciliar(Base):
    def setUp(self) -> None:
        super().setUp()
        self.licenca([conta(), maria()])
        self.entrar(login="maria", usuario=maria(), usuarios=[conta(), maria()])

    def test_nada_mudou(self) -> None:
        self.assertFalse(self.servico.reconciliar())

    def test_permissao_mudou_nao_derruba(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(modulos=["vendas", "agenda"])]))
        self.assertFalse(self.servico.reconciliar())
        self.assertTrue(self.servico.permite_modulo("agenda"))

    def test_conta_bloqueada_sai(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(ativo=False)]))
        self.assertTrue(self.servico.reconciliar())

    def test_conta_apagada_sai(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta()]))
        self.assertTrue(self.servico.reconciliar())

    def test_senha_redefinida_sai(self) -> None:
        self.licencas.guardar_acesso(pacote_acesso([conta(), maria(senha_versao=2)]))
        self.assertTrue(self.servico.reconciliar())

    def test_a_propria_troca_nao_derruba(self) -> None:
        nova = maria(senha_versao=2)
        self.servidor.respostas["trocar-senha"] = {
            "ok": True, "usuario": nova, "acesso_assinado": pacote_acesso([conta(), nova])}
        self.servico.aplicar(self.servico.trocar_senha("cavalo-azul", "outra-senha-boa", True))
        self.assertFalse(self.servico.reconciliar())
        self.servidor.erro = SemConexao("sem rede")
        self.servico.sair(esquecer=True)
        self.assertEqual(self.servico.aplicar(self.servico.entrar("maria", "outra-senha-boa", False)).id, MARIA,
                         "a senha nova ja vale offline")


class Validacoes(unittest.TestCase):
    def test_o_painel_conhece_todos_os_avisos_do_hub(self) -> None:
        """Aviso novo no Hub sem entrar no painel: funcionario criado la nao o veria."""
        painel = (Path(__file__).parent.parent / "painel" / "js" / "acessos.js").read_text(encoding="utf-8")
        for tipo in TIPOS:
            self.assertRegex(painel, rf'{tipo.app_id}: \[[^\]]*"{tipo.chave}"', tipo.chave)

    def test_senha(self) -> None:
        self.assertEqual(validar_senha("cavalo-azul", "dona"), "")
        self.assertIn("8 caracteres", validar_senha("curta"))
        self.assertIn("72", validar_senha("x" * 73))
        self.assertIn("login", validar_senha("dona.loja", "dona.loja"))
        self.assertIn("fácil", validar_senha("12345678"))
        self.assertIn("fácil", validar_senha("aaaaaaaa"))

    def test_login(self) -> None:
        self.assertEqual(validar_login("dona.loja"), "")
        self.assertEqual(validar_login("eric@gmail.com"), "")
        self.assertNotEqual(validar_login("ab"), "")
        self.assertNotEqual(validar_login("com espaco"), "")
        self.assertNotEqual(validar_login("joão"), "")

    def test_forca(self) -> None:
        self.assertEqual(forca_da_senha("123"), 0)
        self.assertEqual(forca_da_senha("abcdefgh"), 1)
        self.assertEqual(forca_da_senha("abcdefgh12"), 2)
        self.assertEqual(forca_da_senha("Cavalo-azul-99"), 3)

    def test_modelos_marcam_modulos_e_avisos_deles(self) -> None:
        modulos, avisos = nucleo.permissoes_do_modelo("Estoque")
        self.assertEqual(modulos, ("estoque",))
        self.assertIn("estoque_baixo", avisos)
        self.assertNotIn("conta_vencida", avisos)
        self.assertEqual(nucleo.permissoes_do_modelo("Não existe"), ((), ()))


if __name__ == "__main__":
    unittest.main()
