"""Os dados da empresa do cliente.

Sem isto, o comprovante que a loja entrega ao cliente dela sai anonimo: so
"COMPROVANTE DE VENDA", sem nome, sem telefone, sem endereco. O documento e o
unico pedaco do software que o cliente do cliente enxerga - e ele estava sem
identidade nenhuma.

Fica nas preferencias (`hub.json`), nao num banco: e um punhado de campos que
vale para a plataforma inteira, nao um cadastro com varias linhas.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, fields
from pathlib import Path

from .documentos import (
    documento_valido,
    formatar_documento,
    formatar_telefone,
    tipo_documento,
)
from .pagamentos import formas_ocultas, pix_confirmada
from .paths import DataPaths, get_paths

SECAO = "empresa"
#: o logotipo e copiado para ca; o cliente pode apagar o original a vontade
LOGO = "logotipo.png"

FORMATOS_LOGO = (".png", ".jpg", ".jpeg", ".bmp")

#: campos que a tela Minha empresa nao grava (ver `core/pagamentos.py`)
_DE_PAGAMENTOS = ("pix_chave", "formas_ocultas")


class EmpresaError(Exception):
    """Erro de preenchimento (mensagem pronta para o usuario)."""


@dataclass
class Empresa:
    """Quem assina os documentos."""

    nome: str = ""
    razao_social: str = ""
    documento: str = ""
    telefone: str = ""
    whatsapp: str = ""
    email: str = ""
    endereco: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    #: linha livre no rodape dos documentos (garantia, condicoes, agradecimento)
    rodape: str = ""
    logo: str = ""
    #: chave Pix do lojista - e dela que nasce o QR Code do balcao. NAO mora na
    #: secao "empresa": vem assinada da area de Pagamentos (`core/pagamentos.py`)
    pix_chave: str = ""
    #: formas de pagamento escondidas no Receber (tambem de Pagamentos)
    formas_ocultas: tuple = ()

    # ------------------------------------------------------------------ leitura
    @property
    def preenchida(self) -> bool:
        """O minimo para o documento deixar de ser anonimo."""
        return bool(self.nome.strip())

    @property
    def documento_formatado(self) -> str:
        return formatar_documento(self.documento)

    @property
    def tipo_documento(self) -> str:
        """CNPJ ou CPF - contado pelos digitos, nao pelo texto digitado."""
        return tipo_documento(self.documento)

    @property
    def telefone_formatado(self) -> str:
        return formatar_telefone(self.telefone)

    @property
    def whatsapp_formatado(self) -> str:
        return formatar_telefone(self.whatsapp or self.telefone)

    @property
    def endereco_completo(self) -> str:
        """Uma linha so, pulando o que estiver vazio."""
        rua = ", ".join(p for p in (self.endereco.strip(), self.numero.strip()) if p)
        partes = [
            ", ".join(p for p in (rua, self.bairro.strip()) if p),
            "/".join(p for p in (self.cidade.strip(), self.uf.strip()) if p),
        ]
        texto = " - ".join(p for p in partes if p)
        cep = _cep(self.cep)
        return f"{texto} - CEP {cep}" if texto and cep else texto or cep

    @property
    def contato(self) -> str:
        """Telefone e e-mail numa linha, para o cabecalho do documento."""
        partes = [self.telefone_formatado, self.email.strip()]
        return "  ".join(p for p in partes if p)

    def caminho_logo(self, paths: DataPaths | None = None) -> Path | None:
        if not self.logo:
            return None
        caminho = Path(self.logo)
        if not caminho.is_absolute():
            caminho = (paths or get_paths()).config_dir / caminho
        return caminho if caminho.exists() else None

    # ------------------------------------------------------------------ escrita
    def validar(self) -> None:
        if self.documento and not documento_valido(self.documento):
            raise EmpresaError("O CNPJ ou CPF informado não é válido.")
        if self.uf and len(self.uf.strip()) != 2:
            raise EmpresaError("A UF tem duas letras (ex.: SP).")

    @property
    def tem_pix(self) -> bool:
        """O balcao so mostra o QR Code quando ha chave cadastrada."""
        return bool(self.pix_chave.strip())

    # ----------------------------------------------------------------- persistir
    @classmethod
    def carregar(cls, settings) -> "Empresa":
        dados = {
            campo.name: settings.get(SECAO, campo.name, "") or ""
            for campo in fields(cls)
            if campo.name not in _DE_PAGAMENTOS
        }
        return cls(**dados, pix_chave=pix_confirmada(settings),
                   formas_ocultas=formas_ocultas(settings))

    def salvar(self, settings) -> "Empresa":
        self.validar()
        self.documento = _so_digitos(self.documento)
        self.telefone = _so_digitos(self.telefone)
        self.whatsapp = _so_digitos(self.whatsapp)
        self.cep = _so_digitos(self.cep)
        self.uf = self.uf.strip().upper()
        for campo in fields(self):
            if campo.name in _DE_PAGAMENTOS:
                continue  # so a area de Pagamentos grava isto, e assinado
            valor = getattr(self, campo.name)
            settings.set(SECAO, campo.name, valor.strip() if isinstance(valor, str) else valor)
        settings.save()
        return self


def guardar_logo(origem: Path, paths: DataPaths | None = None) -> str:
    """Copia o logotipo para a pasta do programa e devolve o nome do arquivo.

    Copiar em vez de apontar: o cliente troca a foto de lugar, esvazia a pasta
    de downloads, e o documento continuaria procurando um arquivo que sumiu.
    """
    origem = Path(origem)
    if origem.suffix.lower() not in FORMATOS_LOGO:
        raise EmpresaError(
            "Escolha uma imagem PNG ou JPG."
        )
    if not origem.exists():
        raise EmpresaError("Não encontrei essa imagem.")

    paths = (paths or get_paths()).ensure()
    destino = paths.config_dir / LOGO
    try:
        shutil.copyfile(origem, destino)
    except OSError as erro:
        raise EmpresaError(f"Não foi possível usar essa imagem: {erro}") from erro
    return LOGO


def apagar_logo(paths: DataPaths | None = None) -> None:
    (paths or get_paths()).config_dir.joinpath(LOGO).unlink(missing_ok=True)


def _so_digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _cep(valor: str) -> str:
    digitos = _so_digitos(valor)
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else digitos
