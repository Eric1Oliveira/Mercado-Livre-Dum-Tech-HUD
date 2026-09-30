"""Digitou o CEP, o endereco aparece - e quando nao aparece, nada quebra."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error

from dumtech.core import cep


class FalsaResposta(io.BytesIO):
    """O que o urlopen devolve, no minimo que o codigo usa."""

    def __enter__(self):
        return self

    def __exit__(self, *_erro) -> bool:
        return False


def responder(corpo: dict):
    def abrir(_pedido, timeout=0):
        return FalsaResposta(json.dumps(corpo).encode("utf-8"))
    return abrir


def falhar(erro):
    def abrir(_pedido, timeout=0):
        raise erro
    return abrir


CENTRO = {
    "cep": "01001-000", "logradouro": "Praca da Se", "bairro": "Se",
    "localidade": "Sao Paulo", "uf": "SP",
}


class CepTestCase(unittest.TestCase):
    def setUp(self) -> None:
        cep.esquecer()

    def test_formata_enquanto_digita(self) -> None:
        self.assertEqual(cep.formatar("0100"), "0100")
        self.assertEqual(cep.formatar("01001000"), "01001-000")
        self.assertEqual(cep.formatar("01001-000"), "01001-000")
        self.assertEqual(cep.formatar("abc01001000xyz"), "01001-000")

    def test_so_pergunta_com_oito_digitos(self) -> None:
        self.assertFalse(cep.completo("0100100"))
        self.assertTrue(cep.completo("01001-000"))
        self.assertIsNone(cep.buscar("0100100", abrir=falhar(AssertionError("nao perguntar"))))

    def test_traz_o_endereco(self) -> None:
        achado = cep.buscar("01001-000", abrir=responder(CENTRO))
        self.assertEqual(achado.logradouro, "Praca da Se")
        self.assertEqual(achado.bairro, "Se")
        self.assertEqual(achado.cidade, "Sao Paulo")
        self.assertEqual(achado.uf, "SP")
        self.assertEqual(achado.cep, "01001-000")

    def test_sem_internet_nao_quebra_o_cadastro(self) -> None:
        erro = urllib.error.URLError("sem rede")
        self.assertIsNone(cep.buscar("01001-000", abrir=falhar(erro)))

    def test_resposta_estranha_nao_quebra(self) -> None:
        def abrir(_pedido, timeout=0):
            return FalsaResposta(b"<html>manutencao</html>")
        self.assertIsNone(cep.buscar("01001-000", abrir=abrir))

    def test_cep_que_nao_existe(self) -> None:
        self.assertIsNone(cep.buscar("99999-999", abrir=responder({"erro": True})))

    def test_cep_de_cidade_inteira_vale_pela_cidade(self) -> None:
        """CEP geral nao tem rua; cidade e UF ja poupam digitacao."""
        achado = cep.buscar("13480-000", abrir=responder(
            {"logradouro": "", "bairro": "", "localidade": "Limeira", "uf": "SP"}))
        self.assertEqual(achado.cidade, "Limeira")
        self.assertEqual(achado.logradouro, "")

    def test_o_mesmo_cep_nao_e_perguntado_duas_vezes(self) -> None:
        vezes = []

        def abrir(_pedido, timeout=0):
            vezes.append(1)
            return FalsaResposta(json.dumps(CENTRO).encode("utf-8"))

        cep.buscar("01001-000", abrir=abrir)
        cep.buscar("01001000", abrir=abrir)
        self.assertEqual(len(vezes), 1)


if __name__ == "__main__":
    unittest.main()
