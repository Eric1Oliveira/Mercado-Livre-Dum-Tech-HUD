"""Agenda de clientes compartilhada pela plataforma.

Fica em `data/plataforma.db` e nao pertence a nenhum aplicativo: o DumTech
Clientes e a tela que administra esses dados, e os demais aplicativos usam a
lista apenas como sugestao ao digitar o nome do cliente. Assim ninguem depende
de ninguem: quem nao tiver o Clientes continua digitando o nome na mao.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from sqlite3 import Row

from . import eventos
from .database import Database, Migration
from .documentos import (
    documento_valido,
    formatar_cep,
    formatar_documento,
    formatar_telefone,
    so_digitos,
    tipo_documento,
)
from .errors import RegraError
from .paths import get_paths

#: a agenda nao e de nenhum aplicativo, mas quem escuta a reconhece por este
#: nome - e o mesmo app_id do DumTech Clientes, a tela que a administra
APP_ID = "clientes"

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)

MIGRATIONS = (
    Migration(
        version=1,
        name="agenda de clientes",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS contatos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT NOT NULL,
                documento     TEXT NOT NULL DEFAULT '',
                telefone      TEXT NOT NULL DEFAULT '',
                email         TEXT NOT NULL DEFAULT '',
                endereco      TEXT NOT NULL DEFAULT '',
                cidade        TEXT NOT NULL DEFAULT '',
                observacoes   TEXT NOT NULL DEFAULT '',
                criado_em     TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_contatos_nome ON contatos(nome);
            """,
        ),
    ),
    Migration(
        version=2,
        name="ficha completa do cliente e anotacoes",
        statements=(
            # ALTER TABLE ADD COLUMN e barato e nao reescreve a tabela: os
            # dados de quem ja usava continuam onde estao.
            """
            ALTER TABLE contatos ADD COLUMN whatsapp    TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN cep         TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN numero      TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN complemento TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN bairro      TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN uf          TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN nascimento  TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN segmento    TEXT NOT NULL DEFAULT '';
            ALTER TABLE contatos ADD COLUMN ativo       INTEGER NOT NULL DEFAULT 1;

            CREATE INDEX IF NOT EXISTS idx_contatos_ativo ON contatos(ativo);
            CREATE INDEX IF NOT EXISTS idx_contatos_documento ON contatos(documento);

            -- o que foi combinado com o cliente, com data: a memoria do
            -- atendimento que hoje se perde num campo de observacoes solto
            CREATE TABLE IF NOT EXISTS contato_notas (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                contato_id INTEGER NOT NULL REFERENCES contatos(id) ON DELETE CASCADE,
                texto      TEXT NOT NULL,
                criado_em  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notas_contato ON contato_notas(contato_id);
            """,
        ),
    ),
)


class ContatoError(RegraError):
    """Erro de regra do cadastro de clientes."""


@dataclass
class Nota:
    """Uma anotacao datada sobre o cliente."""

    id: int | None = None
    contato_id: int | None = None
    texto: str = ""
    criado_em: str = ""

    @classmethod
    def from_row(cls, row: Row) -> "Nota":
        return cls(**{chave: row[chave] for chave in row.keys()})


@dataclass
class Contato:
    id: int | None = None
    nome: str = ""
    documento: str = ""
    telefone: str = ""
    whatsapp: str = ""
    email: str = ""
    cep: str = ""
    endereco: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    nascimento: str = ""
    segmento: str = ""
    ativo: bool = True
    observacoes: str = ""
    criado_em: str = ""
    atualizado_em: str = ""

    # ------------------------------------------------------------- formatacao
    @property
    def documento_formatado(self) -> str:
        return formatar_documento(self.documento)

    @property
    def tipo_documento(self) -> str:
        return tipo_documento(self.documento)

    @property
    def telefone_formatado(self) -> str:
        return formatar_telefone(self.telefone)

    @property
    def whatsapp_formatado(self) -> str:
        return formatar_telefone(self.whatsapp)

    @property
    def cep_formatado(self) -> str:
        return formatar_cep(self.cep)

    @property
    def endereco_completo(self) -> str:
        """Endereco numa linha so, pulando o que estiver vazio."""
        rua = ", ".join(p for p in (self.endereco, self.numero) if p.strip())
        if self.complemento.strip():
            rua = f"{rua} - {self.complemento}" if rua else self.complemento
        municipio = "/".join(p for p in (self.cidade, self.uf) if p.strip())
        partes = [p for p in (rua, self.bairro, municipio, self.cep_formatado) if p.strip()]
        return "  ·  ".join(partes)

    @property
    def resumo(self) -> str:
        partes = [parte for parte in (self.telefone_formatado, self.cidade) if parte]
        return "  -  ".join(partes)

    # ---------------------------------------------------------- aniversario
    @property
    def aniversario(self) -> tuple[int, int] | None:
        """(dia, mes) do aniversario, ou None."""
        try:
            data = date.fromisoformat(self.nascimento)
        except (TypeError, ValueError):
            return None
        return data.day, data.month

    @property
    def idade(self) -> int | None:
        try:
            nascimento = date.fromisoformat(self.nascimento)
        except (TypeError, ValueError):
            return None
        hoje = date.today()
        anos = hoje.year - nascimento.year
        if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
            anos -= 1
        return anos if 0 <= anos < 130 else None

    @property
    def idade_neste_ano(self) -> int | None:
        """Quantos anos ele faz (ou fez) neste ano.

        E o numero certo para a lista de aniversariantes do mes, tenha o
        aniversario ja passado ou nao.
        """
        try:
            nascimento = date.fromisoformat(self.nascimento)
        except (TypeError, ValueError):
            return None
        anos = date.today().year - nascimento.year
        return anos if 0 <= anos < 130 else None

    @classmethod
    def from_row(cls, row: Row) -> "Contato":
        dados = {chave: row[chave] for chave in row.keys()}
        dados["ativo"] = bool(dados.get("ativo", 1))
        return cls(**dados)


@dataclass
class ResumoClientes:
    """Numeros do painel do DumTech Clientes."""

    total: int = 0
    ativos: int = 0
    novos_mes: int = 0
    cidades: int = 0
    aniversariantes: list[Contato] = field(default_factory=list)
    recentes: list[Contato] = field(default_factory=list)
    por_cidade: list[tuple[str, int]] = field(default_factory=list)


CAMPOS = (
    "nome", "documento", "telefone", "whatsapp", "email", "cep", "endereco",
    "numero", "complemento", "bairro", "cidade", "uf", "nascimento",
    "segmento", "ativo", "observacoes",
)


class ContactsStore:
    """Leitura e escrita da agenda de clientes."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db = Database(db_path or get_paths().platform_db, MIGRATIONS)

    # ------------------------------------------------------------------ leitura
    def listar(
        self,
        busca: str = "",
        cidade: str = "",
        segmento: str = "",
        incluir_inativos: bool = False,
    ) -> list[Contato]:
        sql = "SELECT * FROM contatos WHERE 1 = 1"
        params: list = []
        if not incluir_inativos:
            sql += " AND ativo = 1"
        if busca.strip():
            sql += (
                " AND (nome LIKE ? OR documento LIKE ? OR telefone LIKE ?"
                " OR whatsapp LIKE ? OR email LIKE ? OR cidade LIKE ?"
                " OR bairro LIKE ? OR segmento LIKE ?)"
            )
            alvo = f"%{busca.strip()}%"
            params += [alvo] * 8
        if cidade.strip():
            sql += " AND cidade = ?"
            params.append(cidade.strip())
        if segmento.strip():
            sql += " AND segmento = ?"
            params.append(segmento.strip())
        sql += " ORDER BY nome COLLATE NOCASE"
        return [Contato.from_row(row) for row in self.db.query(sql, params)]

    def nomes(self) -> list[str]:
        """Lista de nomes para as sugestoes dos outros aplicativos."""
        return [
            row["nome"]
            for row in self.db.query(
                "SELECT nome FROM contatos WHERE ativo = 1 ORDER BY nome COLLATE NOCASE"
            )
        ]

    def obter(self, contato_id: int) -> Contato | None:
        row = self.db.query_one("SELECT * FROM contatos WHERE id = ?", (contato_id,))
        return Contato.from_row(row) if row else None

    def por_nome(self, nome: str) -> Contato | None:
        """Usado pelos outros aplicativos para puxar telefone e endereco."""
        row = self.db.query_one(
            "SELECT * FROM contatos WHERE nome = ? COLLATE NOCASE", (nome.strip(),)
        )
        return Contato.from_row(row) if row else None

    def por_documento(self, documento: str) -> Contato | None:
        digitos = so_digitos(documento)
        if not digitos:
            return None
        row = self.db.query_one("SELECT * FROM contatos WHERE documento = ?", (digitos,))
        return Contato.from_row(row) if row else None

    def cidades(self) -> list[str]:
        return self._distintos("cidade")

    def segmentos(self) -> list[str]:
        return self._distintos("segmento")

    def _distintos(self, coluna: str) -> list[str]:
        return [
            row["valor"]
            for row in self.db.query(
                f"SELECT DISTINCT {coluna} AS valor FROM contatos "
                f"WHERE TRIM({coluna}) <> '' ORDER BY {coluna} COLLATE NOCASE"
            )
        ]

    # ------------------------------------------------------------------ escrita
    def criar(self, contato: Contato) -> Contato:
        self._validar(contato)
        agora = _agora()
        colunas = ", ".join(CAMPOS)
        marcadores = ", ".join("?" for _ in CAMPOS)
        cursor = self.db.execute(
            f"INSERT INTO contatos ({colunas}, criado_em, atualizado_em) "
            f"VALUES ({marcadores}, ?, ?)",
            (*self._valores(contato), agora, agora),
        )
        contato.id = int(cursor.lastrowid)
        contato.criado_em = contato.atualizado_em = agora
        eventos.avisar(APP_ID)
        return contato

    def atualizar(self, contato: Contato) -> Contato:
        if contato.id is None:
            raise ContatoError("Cliente sem identificação.")
        self._validar(contato)
        agora = _agora()
        atribuicoes = ", ".join(f"{campo} = ?" for campo in CAMPOS)
        self.db.execute(
            f"UPDATE contatos SET {atribuicoes}, atualizado_em = ? WHERE id = ?",
            (*self._valores(contato), agora, contato.id),
        )
        contato.atualizado_em = agora
        eventos.avisar(APP_ID)
        return contato

    def inativar(self, contato_id: int) -> None:
        self.db.execute(
            "UPDATE contatos SET ativo = 0, atualizado_em = ? WHERE id = ?",
            (_agora(), contato_id),
        )
        eventos.avisar(APP_ID)

    def reativar(self, contato_id: int) -> None:
        self.db.execute(
            "UPDATE contatos SET ativo = 1, atualizado_em = ? WHERE id = ?",
            (_agora(), contato_id),
        )
        eventos.avisar(APP_ID)

    def excluir(self, contato_id: int) -> None:
        self.db.execute("DELETE FROM contatos WHERE id = ?", (contato_id,))
        eventos.avisar(APP_ID)

    # ---------------------------------------------------------------- validacao
    def _validar(self, contato: Contato) -> None:
        if not contato.nome.strip():
            raise ContatoError("Informe o nome do cliente.")
        if not documento_valido(contato.documento):
            raise ContatoError(
                "CPF ou CNPJ inválido. Confira os números - o documento é "
                "conferido pelo dígito verificador."
            )
        uf = contato.uf.upper().strip()
        if uf and uf not in UFS:
            raise ContatoError(f"UF '{contato.uf}' não existe.")
        if contato.nascimento.strip():
            try:
                nascimento = date.fromisoformat(contato.nascimento.strip())
            except ValueError as exc:
                raise ContatoError("Data de nascimento inválida.") from exc
            if nascimento > date.today():
                raise ContatoError("A data de nascimento não pode estar no futuro.")

        digitos = so_digitos(contato.documento)
        if digitos:
            existente = self.por_documento(digitos)
            if existente is not None and existente.id != contato.id:
                raise ContatoError(
                    f"O documento {formatar_documento(digitos)} já está cadastrado "
                    f"em '{existente.nome}'."
                )

    @staticmethod
    def _valores(contato: Contato) -> tuple:
        return (
            contato.nome.strip(),
            so_digitos(contato.documento),          # guardado limpo, exibido formatado
            so_digitos(contato.telefone),
            so_digitos(contato.whatsapp),
            contato.email.strip(),
            so_digitos(contato.cep),
            contato.endereco.strip(),
            contato.numero.strip(),
            contato.complemento.strip(),
            contato.bairro.strip(),
            contato.cidade.strip(),
            contato.uf.upper().strip(),
            contato.nascimento.strip(),
            contato.segmento.strip(),
            1 if contato.ativo else 0,
            contato.observacoes.strip(),
        )

    # -------------------------------------------------------------- anotacoes
    def notas(self, contato_id: int) -> list[Nota]:
        return [
            Nota.from_row(row)
            for row in self.db.query(
                "SELECT * FROM contato_notas WHERE contato_id = ? "
                "ORDER BY datetime(criado_em) DESC, id DESC",
                (contato_id,),
            )
        ]

    def anotar(self, contato_id: int, texto: str) -> Nota:
        texto = texto.strip()
        if not texto:
            raise ContatoError("Escreva a anotação antes de salvar.")
        if self.obter(contato_id) is None:
            raise ContatoError("Cliente não encontrado.")
        agora = _agora()
        cursor = self.db.execute(
            "INSERT INTO contato_notas (contato_id, texto, criado_em) VALUES (?, ?, ?)",
            (contato_id, texto, agora),
        )
        eventos.avisar(APP_ID)
        return Nota(int(cursor.lastrowid), contato_id, texto, agora)

    def excluir_nota(self, nota_id: int) -> None:
        self.db.execute("DELETE FROM contato_notas WHERE id = ?", (nota_id,))
        eventos.avisar(APP_ID)

    # ------------------------------------------------------------------ painel
    def aniversariantes(self, mes: int | None = None) -> list[Contato]:
        """Quem faz aniversario no mes - motivo de ligacao que gera venda."""
        mes = mes or date.today().month
        return [
            Contato.from_row(row)
            for row in self.db.query(
                "SELECT * FROM contatos WHERE ativo = 1 AND nascimento <> '' "
                "AND CAST(strftime('%m', nascimento) AS INTEGER) = ? "
                "ORDER BY CAST(strftime('%d', nascimento) AS INTEGER)",
                (int(mes),),
            )
        ]

    def resumo(self, limite: int = 7) -> ResumoClientes:
        mes_atual = datetime.now().strftime("%Y-%m")
        por_cidade = [
            (row["cidade"], int(row["quantidade"]))
            for row in self.db.query(
                "SELECT cidade, COUNT(*) AS quantidade FROM contatos "
                "WHERE ativo = 1 AND TRIM(cidade) <> '' "
                "GROUP BY cidade ORDER BY quantidade DESC, cidade COLLATE NOCASE LIMIT ?",
                (limite,),
            )
        ]
        recentes = [
            Contato.from_row(row)
            for row in self.db.query(
                "SELECT * FROM contatos WHERE ativo = 1 "
                "ORDER BY datetime(criado_em) DESC, id DESC LIMIT ?",
                (limite,),
            )
        ]
        return ResumoClientes(
            total=self.total(incluir_inativos=True),
            ativos=self.total(),
            novos_mes=int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM contatos WHERE substr(criado_em, 1, 7) = ?",
                    (mes_atual,),
                )
            ),
            cidades=int(
                self.db.scalar(
                    "SELECT COUNT(DISTINCT cidade) FROM contatos "
                    "WHERE ativo = 1 AND TRIM(cidade) <> ''"
                )
            ),
            aniversariantes=self.aniversariantes()[:limite],
            recentes=recentes,
            por_cidade=por_cidade,
        )

    def exportar_csv(self, incluir_inativos: bool = True) -> str:
        """A carteira de clientes num arquivo - para o contador, o e-mail, o backup."""
        import csv
        import io

        colunas = [
            "nome", "documento", "telefone", "whatsapp", "email", "nascimento",
            "cep", "endereco", "numero", "complemento", "bairro", "cidade", "uf",
            "segmento", "ativo", "observacoes", "cadastrado_em",
        ]
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(colunas)
        for c in self.listar(incluir_inativos=incluir_inativos):
            escritor.writerow([
                c.nome, c.documento_formatado, c.telefone_formatado,
                c.whatsapp_formatado, c.email, c.nascimento, c.cep_formatado,
                c.endereco, c.numero, c.complemento, c.bairro, c.cidade, c.uf,
                c.segmento, "sim" if c.ativo else "nao", c.observacoes, c.criado_em,
            ])
        return saida.getvalue()

    def total(self, incluir_inativos: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM contatos"
        if not incluir_inativos:
            sql += " WHERE ativo = 1"
        return int(self.db.scalar(sql))

    def close(self) -> None:
        self.db.close()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")
