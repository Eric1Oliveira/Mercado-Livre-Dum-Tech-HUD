"""Licenca assinada: o Hub confere se a licenca veio mesmo da DumTech.

POR QUE EXISTE
    O ``license.json`` e um arquivo comum no computador do cliente. Sem
    assinatura, bastava editar a lista de modulos (ou copiar o arquivo para
    outro computador) para liberar tudo offline.

COMO FUNCIONA
    A Edge Function ``licenca-assinada`` monta a licenca (chave, computador,
    modulos, prazo) e ASSINA com uma chave privada Ed25519 que so existe no
    servidor. O Hub guarda o pacote assinado e, toda vez que carrega a licenca,
    confere com a chave PUBLICA abaixo. Mudou um byte, a assinatura nao bate.

    O Hub nunca assina nada: aqui so ha a conferencia (RFC 8032, secao 6), em
    Python puro - o projeto evita dependencia nativa no instalador.

O QUE A ASSINATURA NAO RESOLVE (limite honesto)
    Programa alterado para pular a conferencia, e relogio atrasado para esticar
    o prazo offline. Isso exige mexer no executavel - outro nivel de esforco.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

#: kid -> chave publica Ed25519 (32 bytes, hex). Gerada por
#: tools/gerar_chave_licenca.mjs; a privada correspondente mora so no segredo da
#: Edge Function. Para trocar de chave, ACRESCENTE a nova (k2) sem tirar a antiga.
CHAVES_PUBLICAS: dict[str, str] = {
    "k1": "db64f3dbb5b65ec9e7c055409b346c891ddd8598ee5cc9de277f356b40cc058f",
}

# ================================================================ Ed25519 ====
# Verificacao da RFC 8032 (secao 6), com os resultados reduzidos mod p a cada
# passo. Pontos em coordenadas estendidas (X, Y, Z, T): x = X/Z, y = Y/Z.
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_RAIZ_MENOS_1 = pow(2, (_P - 1) // 4, _P)


def _soma(a: tuple, b: tuple) -> tuple:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    k_a = (y1 - x1) * (y2 - x2) % _P
    k_b = (y1 + x1) * (y2 + x2) % _P
    k_c = 2 * t1 * t2 * _D % _P
    k_d = 2 * z1 * z2 % _P
    e, f, g, h = k_b - k_a, k_d - k_c, k_d + k_c, k_b + k_a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiplica(escalar: int, ponto: tuple) -> tuple:
    resultado = (0, 1, 1, 0)  # elemento neutro
    while escalar > 0:
        if escalar & 1:
            resultado = _soma(resultado, ponto)
        ponto = _soma(ponto, ponto)
        escalar >>= 1
    return resultado


def _iguais(a: tuple, b: tuple) -> bool:
    return ((a[0] * b[2] - b[0] * a[2]) % _P == 0
            and (a[1] * b[2] - b[1] * a[2]) % _P == 0)


def _recuperar_x(y: int, sinal: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_MENOS_1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


def _descomprimir(dados: bytes) -> tuple | None:
    if len(dados) != 32:
        return None
    y = int.from_bytes(dados, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, sinal)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recuperar_x(_GY, 0)
_BASE = (_GX, _GY, 1, _GX * _GY % _P)


def verificar_ed25519(publica: bytes, mensagem: bytes, assinatura: bytes) -> bool:
    """True se `assinatura` foi feita sobre `mensagem` pela dona de `publica`."""
    if len(publica) != 32 or len(assinatura) != 64:
        return False
    ponto_a = _descomprimir(publica)
    if ponto_a is None:
        return False
    r_bytes = assinatura[:32]
    ponto_r = _descomprimir(r_bytes)
    if ponto_r is None:
        return False
    s = int.from_bytes(assinatura[32:], "little")
    if s >= _Q:  # assinatura maleavel: recusada
        return False
    h = int.from_bytes(hashlib.sha512(r_bytes + publica + mensagem).digest(), "little") % _Q
    return _iguais(_multiplica(s, _BASE), _soma(ponto_r, _multiplica(h, ponto_a)))


# ============================================================ o pacote ====
def _base64url(texto: str) -> bytes:
    texto = str(texto or "")
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def abrir(pacote: dict, chaves: dict[str, str] | None = None) -> dict | None:
    """Devolve o conteudo da licenca se a assinatura bater; senao None.

    `pacote` = {"v": 1, "kid": "k1", "licenca": <base64url>, "assinatura": <base64url>}
    A conferencia e feita sobre os BYTES recebidos (nada de remontar o JSON),
    e so depois eles viram dicionario.
    """
    if not isinstance(pacote, dict):
        return None
    publica_hex = (chaves or CHAVES_PUBLICAS).get(str(pacote.get("kid") or ""))
    if not publica_hex:
        return None
    try:
        conteudo = _base64url(pacote.get("licenca"))
        assinatura = _base64url(pacote.get("assinatura"))
        if not verificar_ed25519(bytes.fromhex(publica_hex), conteudo, assinatura):
            return None
        dados = json.loads(conteudo.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(dados, dict) or dados.get("v") != 1 or dados.get("kid") != pacote.get("kid"):
        return None
    return dados


def vencida(dados: dict, agora: datetime | None = None) -> bool:
    """A licenca assinada tem prazo para ser conferida de novo (uso offline)."""
    try:
        limite = datetime.fromisoformat(str(dados.get("valida_ate")).replace("Z", "+00:00"))
    except ValueError:
        return True
    if limite.tzinfo is None:
        limite = limite.replace(tzinfo=timezone.utc)
    return (agora or datetime.now(timezone.utc)) > limite


# ======================================================== o computador ====
def computador_id() -> str:
    """Identidade deste Windows, estavel e que nao depende da placa de rede.

    O `machine_id` da ativacao mistura o MAC - que muda com VPN, adaptador USB
    ou Wi-Fi ligado. Para prender a licenca ao computador usamos o MachineGuid
    (criado na instalacao do Windows). Ele sai daqui ja embaralhado: o valor
    cru nunca vai para o servidor.
    """
    base = ""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as chave:
                base = str(winreg.QueryValueEx(chave, "MachineGuid")[0])
        except OSError:
            logger.warning("MachineGuid indisponivel; usando o identificador da ativacao")
    if not base:
        from .licensing import machine_id  # import tardio: licensing importa este modulo

        base = machine_id()
    return hashlib.sha256(f"dumtech|{base.strip().lower()}".encode("utf-8")).hexdigest()[:32]
