"""O QR Code do Pix: o payload que o aplicativo do banco le.

Aqui nao ha interface nenhuma - so a cadeia de caracteres que vira o QR. E ela
que decide se o cliente consegue pagar, entao os testes cobrem exatamente os
casos que quebram no balcao: acento no nome da loja, nome comprido demais,
venda sem valor definido e cada tipo de chave.

O ancoradouro do CRC e o vetor de conferencia publicado do proprio algoritmo
(CRC-16/CCITT-FALSE de "123456789" = 0x29B1). Nenhum teste daqui prova que um
banco aceita o QR - isso so um celular de verdade prova.
"""

from __future__ import annotations

import unittest

from dumtech.core.pix import (
    ALEATORIA,
    CNPJ,
    CPF,
    EMAIL,
    TELEFONE,
    CobrancaPix,
    PixError,
    campos,
    crc16,
    normalizar,
    payload,
    tipo_chave,
)


class CrcTestCase(unittest.TestCase):
    def test_vetor_de_conferencia_do_algoritmo(self) -> None:
        """O valor publicado do CRC-16/CCITT-FALSE. Se isto quebra, tudo quebra."""
        self.assertEqual(crc16("123456789"), "29B1")

    def test_sempre_quatro_maiusculas(self) -> None:
        for texto in ("", "a", "00020126", "x" * 500):
            resultado = crc16(texto)
            self.assertEqual(len(resultado), 4, texto[:10])
            self.assertEqual(resultado, resultado.upper())


class TipoDeChaveTestCase(unittest.TestCase):
    def test_reconhece_cada_tipo(self) -> None:
        casos = {
            "111.444.777-35": CPF,
            "11144477735": CPF,
            "11222333000181": CNPJ,
            "11 99999-8888": TELEFONE,
            "loja@exemplo.com.br": EMAIL,
            "123e4567-e12b-12d1-a456-426655440000": ALEATORIA,
        }
        for chave, esperado in casos.items():
            self.assertEqual(tipo_chave(chave), esperado, chave)

    def test_chave_impossivel_nao_tem_tipo(self) -> None:
        for chave in ("", "   ", "abc", "123", "arroba@", "@ponto.com"):
            self.assertEqual(tipo_chave(chave), "", repr(chave))

    def test_normalizar_deixa_a_chave_no_formato_do_pix(self) -> None:
        self.assertEqual(normalizar("111.444.777-35"), "11144477735")
        self.assertEqual(normalizar("11.222.333/0001-81"), "11222333000181")
        self.assertEqual(normalizar("(11) 99999-8888"), "+5511999998888")
        self.assertEqual(normalizar("  Loja@Exemplo.COM.br "), "loja@exemplo.com.br")

    def test_normalizar_recusa_o_que_nao_e_chave(self) -> None:
        with self.assertRaises(PixError):
            normalizar("nao sou uma chave")


class PayloadTestCase(unittest.TestCase):
    def _cobranca(self, **campos_extras) -> CobrancaPix:
        dados = dict(chave="11144477735", beneficiario="Loja Teste",
                     cidade="Sao Paulo", valor=150.0, documento="VEN-2026-0001")
        dados.update(campos_extras)
        return CobrancaPix(**dados)

    def test_o_payload_se_fecha_com_o_proprio_crc(self) -> None:
        texto = payload(self._cobranca())
        self.assertTrue(texto.startswith("000201"))
        corpo, conferencia = texto[:-4], texto[-4:]
        self.assertTrue(corpo.endswith("6304"))
        self.assertEqual(crc16(corpo), conferencia)

    def test_os_campos_obrigatorios_estao_todos_la(self) -> None:
        lidos = campos(payload(self._cobranca()))
        self.assertEqual(lidos["00"], "01")       # formato
        self.assertEqual(lidos["52"], "0000")     # categoria
        self.assertEqual(lidos["53"], "986")      # real
        self.assertEqual(lidos["58"], "BR")       # pais
        self.assertIn("br.gov.bcb.pix", lidos["26"])
        self.assertIn("11144477735", lidos["26"])

    def test_o_valor_vai_com_ponto_e_dois_decimais(self) -> None:
        self.assertEqual(campos(payload(self._cobranca(valor=150.0)))["54"], "150.00")
        self.assertEqual(campos(payload(self._cobranca(valor=7.5)))["54"], "7.50")
        self.assertEqual(campos(payload(self._cobranca(valor=1234.56)))["54"], "1234.56")

    def test_venda_sem_valor_gera_qr_sem_valor(self) -> None:
        """Valido: o cliente digita quanto vai pagar no proprio aplicativo."""
        lidos = campos(payload(self._cobranca(valor=0)))
        self.assertNotIn("54", lidos)

    def test_valor_negativo_nao_passa(self) -> None:
        with self.assertRaises(PixError):
            payload(self._cobranca(valor=-1))

    # ------------------------------------------------- o que quebra no balcao
    def test_acento_sai_do_nome_e_da_cidade(self) -> None:
        lidos = campos(payload(self._cobranca(
            beneficiario="Acougue Sao Joao", cidade="Sao Joao del-Rei")))
        self.assertEqual(lidos["59"], "ACOUGUE SAO JOAO")
        self.assertEqual(lidos["60"], "SAO JOAO DEL-RE")  # cortado em 15

    def test_acento_de_verdade_vira_letra_simples(self) -> None:
        lidos = campos(payload(self._cobranca(
            beneficiario="Açougue Ração", cidade="Ribeirão Preto")))
        self.assertEqual(lidos["59"], "ACOUGUE RACAO")
        self.assertEqual(lidos["60"], "RIBEIRAO PRETO")

    def test_nome_comprido_e_cortado_sem_quebrar_o_campo(self) -> None:
        lidos = campos(payload(self._cobranca(
            beneficiario="Comercio de Materiais de Construcao Silva Ltda")))
        self.assertLessEqual(len(lidos["59"]), 25)
        self.assertTrue(lidos["59"].startswith("COMERCIO DE MATERIAIS"))
        # corte que cai num espaco nao pode deixar sobra no fim: o banco mostra
        self.assertEqual(lidos["59"], lidos["59"].strip())

    def test_loja_sem_nome_nem_cidade_ainda_paga(self) -> None:
        """Nome e cidade nao mudam para onde o dinheiro vai."""
        lidos = campos(payload(self._cobranca(beneficiario="", cidade="")))
        self.assertEqual(lidos["59"], "LOJA")
        self.assertEqual(lidos["60"], "BRASIL")

    def test_o_txid_perde_o_que_nao_e_letra_nem_numero(self) -> None:
        lidos = campos(payload(self._cobranca(documento="VEN-2026-0001")))
        self.assertIn("VEN20260001", lidos["62"])

    def test_venda_sem_numero_usa_o_txid_coringa(self) -> None:
        lidos = campos(payload(self._cobranca(documento="")))
        self.assertIn("***", lidos["62"])

    def test_sem_chave_nao_existe_cobranca(self) -> None:
        with self.assertRaises(PixError):
            payload(self._cobranca(chave=""))

    def test_cada_tipo_de_chave_gera_payload_valido(self) -> None:
        for chave in ("11144477735", "11222333000181", "(11) 99999-8888",
                      "loja@exemplo.com.br",
                      "123e4567-e12b-12d1-a456-426655440000"):
            texto = payload(self._cobranca(chave=chave))
            self.assertEqual(crc16(texto[:-4]), texto[-4:], chave)
            self.assertIn(normalizar(chave), campos(texto)["26"])

    def test_o_tamanho_declarado_bate_com_o_conteudo(self) -> None:
        """Um tamanho errado desalinha tudo que vem depois e o banco recusa."""
        texto = payload(self._cobranca(beneficiario="Açougue Sao Joao"))
        # `campos` so consegue percorrer ate o fim se cada tamanho estiver certo
        lidos = campos(texto)
        self.assertIn("63", lidos)
        self.assertEqual(len(lidos["63"]), 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
