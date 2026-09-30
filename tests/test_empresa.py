"""A identidade da empresa nos documentos.

Sem ela o comprovante que a loja entrega ao cliente dela sai anonimo.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dumtech.core.config import Settings
from dumtech.core.empresa import Empresa, EmpresaError, apagar_logo, guardar_logo
from dumtech.core.paths import DataPaths
from dumtech.ui.recibo import LARGURA, cabecalho_empresa, rodape_empresa

CNPJ = "11.222.333/0001-81"


def _empresa(**campos) -> Empresa:
    dados = dict(
        nome="Casa do Parafuso", razao_social="Casa do Parafuso Ltda",
        documento=CNPJ, telefone="6332258899", email="contato@casa.com.br",
        endereco="Rua das Flores", numero="120", bairro="Centro",
        cidade="Palmas", uf="TO", cep="77000000",
    )
    dados.update(campos)
    return Empresa(**dados)


class EmpresaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(Path(tempfile.mkdtemp()) / "hub.json")
        self.paths = DataPaths(root=Path(tempfile.mkdtemp())).ensure()

    def test_vazia_e_nao_preenchida(self) -> None:
        self.assertFalse(Empresa().preenchida)
        self.assertTrue(_empresa().preenchida)

    def test_o_nome_e_o_minimo(self) -> None:
        """Basta o nome para o documento deixar de ser anonimo."""
        self.assertTrue(Empresa(nome="Loja do Ze").preenchida)

    def test_formata_documento_telefone_e_endereco(self) -> None:
        e = _empresa()
        self.assertEqual(e.documento_formatado, "11.222.333/0001-81")
        self.assertEqual(e.telefone_formatado, "(63) 3225-8899")
        self.assertIn("Rua das Flores, 120", e.endereco_completo)
        self.assertIn("Palmas/TO", e.endereco_completo)
        self.assertIn("77000-000", e.endereco_completo)

    def test_endereco_pula_o_que_esta_vazio(self) -> None:
        magra = Empresa(nome="Loja", cidade="Gurupi")
        self.assertEqual(magra.endereco_completo, "Gurupi")
        self.assertEqual(Empresa(nome="Loja").endereco_completo, "")

    def test_whatsapp_cai_no_telefone_quando_nao_informado(self) -> None:
        self.assertEqual(_empresa().whatsapp_formatado, "(63) 3225-8899")
        outra = _empresa(whatsapp="63988887777")
        self.assertEqual(outra.whatsapp_formatado, "(63) 98888-7777")

    def test_documento_invalido_e_recusado(self) -> None:
        with self.assertRaises(EmpresaError):
            _empresa(documento="11.222.333/0001-99").validar()

    def test_uf_com_tamanho_errado_e_recusada(self) -> None:
        with self.assertRaises(EmpresaError):
            _empresa(uf="Tocantins").validar()

    def test_salva_e_carrega_das_preferencias(self) -> None:
        _empresa().salvar(self.settings)
        lida = Empresa.carregar(self.settings)

        self.assertEqual(lida.nome, "Casa do Parafuso")
        self.assertEqual(lida.cidade, "Palmas")
        # guardado limpo, exibido formatado
        self.assertEqual(lida.documento, "11222333000181")
        self.assertEqual(lida.documento_formatado, "11.222.333/0001-81")
        self.assertEqual(lida.uf, "TO")

    def test_empresa_nunca_preenchida_carrega_vazia(self) -> None:
        self.assertFalse(Empresa.carregar(self.settings).preenchida)


class LogoTestCase(EmpresaTestCase):
    def _imagem(self, nome: str = "logo.png") -> Path:
        arquivo = Path(tempfile.mkdtemp()) / nome
        arquivo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
        return arquivo

    def test_o_logotipo_e_copiado_para_dentro_do_programa(self) -> None:
        """Copiar, nao apontar: o cliente move a foto e o documento continuaria
        procurando um arquivo que sumiu."""
        origem = self._imagem()
        nome = guardar_logo(origem, self.paths)

        guardado = self.paths.config_dir / nome
        self.assertTrue(guardado.exists())

        origem.unlink()  # o cliente apagou o original
        empresa = _empresa(logo=nome)
        self.assertEqual(empresa.caminho_logo(self.paths), guardado)

    def test_formato_errado_e_recusado(self) -> None:
        with self.assertRaises(EmpresaError):
            guardar_logo(self._imagem("logo.pdf"), self.paths)

    def test_imagem_que_nao_existe_e_recusada(self) -> None:
        with self.assertRaises(EmpresaError):
            guardar_logo(Path("nao/existe.png"), self.paths)

    def test_sem_logo_o_caminho_e_nulo(self) -> None:
        self.assertIsNone(_empresa().caminho_logo(self.paths))

    def test_tirar_o_logotipo(self) -> None:
        nome = guardar_logo(self._imagem(), self.paths)
        apagar_logo(self.paths)
        self.assertIsNone(_empresa(logo=nome).caminho_logo(self.paths))


class CabecalhoTestCase(unittest.TestCase):
    """O que entra no papel de 40 colunas."""

    def test_sem_empresa_o_documento_sai_como_saia_antes(self) -> None:
        """O programa tem que ser util no primeiro dia, sem configurar nada."""
        self.assertEqual(cabecalho_empresa(None), [])
        self.assertEqual(cabecalho_empresa(Empresa()), [])
        self.assertEqual(rodape_empresa(Empresa()), [])

    def test_o_cabecalho_leva_nome_documento_endereco_e_contato(self) -> None:
        linhas = cabecalho_empresa(_empresa())
        texto = "\n".join(linhas)

        self.assertIn("CASA DO PARAFUSO", texto)
        self.assertIn("CNPJ: 11.222.333/0001-81", texto)
        self.assertIn("Palmas/TO", texto)
        self.assertIn("(63) 3225-8899", texto)
        self.assertTrue(all(len(linha) <= LARGURA for linha in linhas))

    def test_cpf_aparece_como_cpf(self) -> None:
        texto = "\n".join(cabecalho_empresa(_empresa(documento="52998224725")))
        self.assertIn("CPF: 529.982.247-25", texto)

    def test_razao_social_igual_ao_nome_nao_repete(self) -> None:
        igual = _empresa(razao_social="Casa do Parafuso")
        self.assertEqual(
            "\n".join(cabecalho_empresa(igual)).count("Casa do Parafuso"), 0
        )  # o nome sai em maiusculas; a razao repetida nao entra

    def test_endereco_comprido_quebra_e_fica_centralizado(self) -> None:
        comprida = _empresa(
            endereco="Avenida Presidente Juscelino Kubitschek de Oliveira",
            bairro="Plano Diretor Sul Quadra 104 Sul",
        )
        linhas = cabecalho_empresa(comprida)
        self.assertGreater(len(linhas), 4)
        self.assertTrue(all(len(linha) <= LARGURA for linha in linhas))

    def test_o_rodape_e_a_frase_que_o_cliente_escreve(self) -> None:
        texto = "\n".join(rodape_empresa(_empresa(rodape="Obrigado pela preferencia!")))
        self.assertIn("Obrigado pela preferencia!", texto)


class DocumentosDosModulosTestCase(unittest.TestCase):
    """A empresa aparece nos quatro documentos que ja existiam."""

    def test_comprovante_de_venda(self) -> None:
        from dumtech.apps.vendas.models import ItemVenda, Venda
        from dumtech.apps.vendas.recibo import comprovante

        venda = Venda(numero="VEN-2026-0001", cliente="Maria",
                      itens=[ItemVenda(descricao="Item", valor_unitario=10.0)])
        self.assertNotIn("CASA DO PARAFUSO", comprovante(venda))
        self.assertIn("CASA DO PARAFUSO", comprovante(venda, _empresa()))

    def test_entrada_e_entrega_da_ordem(self) -> None:
        from dumtech.apps.ordens.models import Ordem
        from dumtech.apps.ordens.recibo import entrada, entrega

        ordem = Ordem(numero="OS-2026-0001", cliente="Joao",
                      equipamento="Notebook", defeito="Nao liga")
        for papel in (entrada, entrega):
            self.assertNotIn("CASA DO PARAFUSO", papel(ordem))
            self.assertIn("CASA DO PARAFUSO", papel(ordem, _empresa()))

    def test_proposta_comercial(self) -> None:
        from dumtech.apps.orcamentos.models import ItemOrcamento, Orcamento
        from dumtech.apps.orcamentos.recibo import proposta

        orcamento = Orcamento(numero="ORC-2026-0001", cliente="Mercado",
                              itens=[ItemOrcamento(descricao="Servico",
                                                   valor_unitario=100.0)])
        texto = proposta(orcamento, _empresa(rodape="Validade sujeita a estoque."))
        self.assertIn("CASA DO PARAFUSO", texto)
        self.assertIn("Validade sujeita a estoque.", texto)
        self.assertTrue(all(len(linha) <= LARGURA for linha in texto.splitlines()))


if __name__ == "__main__":
    unittest.main()
