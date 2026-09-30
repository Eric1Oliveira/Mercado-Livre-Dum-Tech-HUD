"""Testes da plataforma: pastas, licenca e catalogo de aplicativos."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.core.hub_store import HubStore
from dumtech.core.licensing import License, LicenseService, is_valid_key_format, machine_id
from dumtech.core.paths import get_paths
from dumtech.core.registry import AppRegistry


class PathsTestCase(unittest.TestCase):
    def test_pastas_sao_criadas(self) -> None:
        paths = get_paths()
        for pasta in (paths.config_dir, paths.data_dir, paths.apps_data_dir, paths.logs_dir):
            self.assertTrue(pasta.exists(), pasta)

    def test_cada_aplicativo_tem_seu_banco(self) -> None:
        paths = get_paths()
        self.assertNotEqual(paths.app_db("estoque"), paths.app_db("financeiro"))
        self.assertEqual(paths.app_db("estoque").name, "estoque.db")


class LicencaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.arquivo = Path(tempfile.mkdtemp()) / "license.json"
        self.service = LicenseService(self.arquivo)

    def test_instalacao_local_libera_os_aplicativos_instalados(self) -> None:
        for app_id in ("estoque", "clientes", "financeiro", "vendas"):
            self.assertTrue(self.service.allows(app_id), app_id)
        self.assertFalse(self.service.allows("juridico"))  # nao existe
        self.assertTrue(self.arquivo.exists())

    def test_licenca_gravada_e_relida(self) -> None:
        from .assinante import assinar_licenca, licenca_de_teste

        # licenca do servidor so e aceita assinada: o assinante de teste faz o papel dele
        nova = assinar_licenca(License(
            key="DUM1-2345-ABCD-6789",
            customer="Joao",
            entitlements=("estoque", "financeiro"),
            machine=machine_id(),
            activated_at="2026-01-01T10:00:00",
            source="supabase",
        ))
        self.service.save(nova)
        with licenca_de_teste():
            outro = LicenseService(self.arquivo)
            self.assertEqual(outro.current.customer, "Joao")
            self.assertTrue(outro.allows("financeiro"))
            self.assertFalse(outro.current.is_local)

    def test_licenca_vencida_bloqueia_o_aplicativo(self) -> None:
        vencida = License(
            key="DUM1-2345-ABCD-6789",
            customer="Joao",
            entitlements=("estoque",),
            machine=machine_id(),
            activated_at="2020-01-01T10:00:00",
            expires_at="2021-01-01T10:00:00+00:00",
        )
        self.assertTrue(vencida.is_expired)
        self.assertFalse(vencida.allows("estoque"))

    def test_formato_da_chave(self) -> None:
        self.assertTrue(is_valid_key_format("DUM1-2345-ABCD-6789"))
        self.assertFalse(is_valid_key_format("DUM1-2345"))
        self.assertFalse(is_valid_key_format(""))


class RegistroTestCase(unittest.TestCase):
    def setUp(self) -> None:
        arquivo = Path(tempfile.mkdtemp()) / "license.json"
        self.service = LicenseService(arquivo)
        self.registry = AppRegistry(self.service)

    APPS_ESPERADOS = {
        "estoque", "clientes", "financeiro", "orcamentos", "vendas", "ordens", "agenda",
    }

    def test_encontra_todos_os_aplicativos_instalados(self) -> None:
        entradas = self.registry.load()
        self.assertEqual({e.app_id for e in entradas}, self.APPS_ESPERADOS)
        self.assertEqual(self.registry.failures, [])
        self.assertEqual(self.registry.get("estoque").manifest.name, "DumTech Estoque")

    def test_todo_aplicativo_tem_manifesto_completo(self) -> None:
        for entrada in self.registry.load():
            manifesto = entrada.manifest
            self.assertTrue(manifesto.name.startswith("DumTech "), manifesto.name)
            self.assertTrue(manifesto.short_name)
            self.assertTrue(manifesto.description)
            self.assertTrue(manifesto.accent.startswith("#"))
            self.assertTrue(callable(entrada.module.create_window))

    def test_apps_liberados_seguem_a_licenca(self) -> None:
        self.assertEqual({e.app_id for e in self.registry.available()}, self.APPS_ESPERADOS)
        self.assertEqual(self.registry.locked(), [])

    def test_licenca_sem_o_app_deixa_ele_bloqueado(self) -> None:
        atual = self.service.current
        self.service.save(License(
            key=atual.key,
            customer=atual.customer,
            entitlements=(),
            machine=atual.machine,
            activated_at=atual.activated_at,
        ))
        self.assertEqual(self.registry.available(), [])
        self.assertEqual({e.app_id for e in self.registry.locked()}, self.APPS_ESPERADOS)

    def test_modulo_de_aplicativo_tem_o_contrato_esperado(self) -> None:
        modulo = self.registry.get("estoque").module
        self.assertTrue(hasattr(modulo, "MANIFEST"))
        self.assertTrue(callable(modulo.create_window))
        self.assertEqual(modulo.MANIFEST.license_code, "ESTOQUE")


class HubStoreTestCase(unittest.TestCase):
    def test_registra_ultima_abertura(self) -> None:
        store = HubStore(Path(tempfile.mkdtemp()) / "hub.db")
        self.assertIsNone(store.last_opened("estoque"))
        store.register_open("estoque")
        self.assertIsNotNone(store.last_opened("estoque"))
        store.close()


if __name__ == "__main__":
    unittest.main()
