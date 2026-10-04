"""Testes de erros HTTP e conexão no Supabase.

Verifica se URLError, TimeoutError e HTTP 500+ são classificados corretamente.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from dumtech.core.supabase import SemConexao, ServicoIndisponivel, SupabaseClient


class ErrosHTTPTestCase(unittest.TestCase):
    """Testes de classificação de erros HTTP."""

    def setUp(self) -> None:
        self.cliente = SupabaseClient(
            url="https://teste.supabase.co/rest/v1",
            anon_key="test-key-123",
        )

    def test_url_error_vira_sem_conexao(self) -> None:
        """URLError (sem internet, DNS, etc.) vira SemConexao com mensagem clara."""
        url_error = urllib.error.URLError("No internet connection")
        with mock.patch("urllib.request.urlopen", side_effect=url_error):
            with self.assertRaises(SemConexao) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("internet", mensagem.lower())
            self.assertIn("rede", mensagem.lower())
            self.assertIn("instantes", mensagem.lower())

    def test_timeout_error_vira_sem_conexao(self) -> None:
        """TimeoutError vira SemConexao com mensagem adequada."""
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(SemConexao) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("demorou", mensagem.lower())
            self.assertIn("instantes", mensagem.lower())

    def test_http_500_vira_servico_indisponivel(self) -> None:
        """HTTP 500 (server error) vira ServicoIndisponivel, não SemConexao."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 500, "Internal Server Error", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            # NÃO deve ser SemConexao (internet OK)
            self.assertNotIsInstance(ctx.exception, SemConexao)
            # Deve mencionar servidor fora do ar
            self.assertIn("servidor", mensagem.lower())
            self.assertIn("fora do ar", mensagem.lower())

    def test_http_502_vira_servico_indisponivel(self) -> None:
        """HTTP 502 (bad gateway) vira ServicoIndisponivel."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 502, "Bad Gateway", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            self.assertNotIsInstance(ctx.exception, SemConexao)

    def test_http_503_vira_servico_indisponivel(self) -> None:
        """HTTP 503 (service unavailable) vira ServicoIndisponivel."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 503, "Service Unavailable", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            # Deve ser ServicoIndisponivel, não SemConexao
            self.assertNotIsInstance(ctx.exception, SemConexao)
            self.assertIn("minutos", mensagem.lower())

    def test_http_404_vira_servico_indisponivel(self) -> None:
        """HTTP 404 (not found) vira ServicoIndisponivel com mensagem específica."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 404, "Not Found", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("migrations", mensagem.lower())
            self.assertIn("preparado", mensagem.lower())

    def test_http_401_vira_servico_indisponivel(self) -> None:
        """HTTP 401 (unauthorized) vira ServicoIndisponivel com mensagem de permissão."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 401, "Unauthorized", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("permissao", mensagem.lower())

    def test_http_403_vira_servico_indisponivel(self) -> None:
        """HTTP 403 (forbidden) vira ServicoIndisponivel com mensagem de permissão."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        http_error = urllib.error.HTTPError(
            "https://test.com", 403, "Forbidden", {}, response_mock
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("permissao", mensagem.lower())

    def test_resposta_nao_json_vira_servico_indisponivel(self) -> None:
        """Resposta não-JSON vira ServicoIndisponivel com mensagem clara."""
        response_mock = mock.Mock()
        response_mock.read.return_value = b"<!DOCTYPE html><html>Error</html>"
        response_mock.status = 200
        response_mock.headers = {}
        response_mock.__enter__ = mock.Mock(return_value=response_mock)
        response_mock.__exit__ = mock.Mock(return_value=None)
        with mock.patch("urllib.request.urlopen", return_value=response_mock):
            with self.assertRaises(ServicoIndisponivel) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception)
            self.assertIn("inesperada", mensagem.lower())
            self.assertIn("minutos", mensagem.lower())

    def test_mensagens_sao_orientadoras(self) -> None:
        """Todas as mensagens devem ter orientação sobre ação (tente, verifique, fale)."""
        # URLError
        response_mock = mock.Mock()
        response_mock.read.return_value = b"{}"
        url_error = urllib.error.URLError("test")
        with mock.patch("urllib.request.urlopen", side_effect=url_error):
            with self.assertRaises(SemConexao) as ctx:
                self.cliente.rpc("teste", {})
            mensagem = str(ctx.exception).lower()
            # Deve ter ação (tente, verifique)
            self.assertTrue(
                "tente" in mensagem or "verifique" in mensagem or "fale" in mensagem,
                f"Mensagem sem ação clara: {ctx.exception}"
            )


if __name__ == "__main__":
    unittest.main()
