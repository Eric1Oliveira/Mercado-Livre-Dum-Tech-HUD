"""Assinante Ed25519 SO para os testes: faz o papel da Edge Function.

O Hub nunca assina nada; a assinatura de verdade vive no servidor
(supabase/functions/licenca-assinada). Aqui os servidores de mentira dos testes
assinam com uma chave de teste, e `licenca_de_teste()` faz o Hub confiar nela -
assim os testes exercitam o caminho real: licenca sem assinatura nao abre.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest import mock

from dumtech.core import assinatura

KID = "t1"
COMPUTADOR = "a" * 32  # o computador_id "deste computador" nos testes
_SEGREDO = hashlib.sha256(b"dumtech-teste").digest()


def _comprimir(ponto: tuple) -> bytes:
    p = assinatura._P
    z_inv = pow(ponto[2], p - 2, p)
    x, y = ponto[0] * z_inv % p, ponto[1] * z_inv % p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _expandir(segredo: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(segredo).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publica_de(segredo: bytes = _SEGREDO) -> bytes:
    return _comprimir(assinatura._multiplica(_expandir(segredo)[0], assinatura._BASE))


def assinar(mensagem: bytes, segredo: bytes = _SEGREDO) -> bytes:
    """Ed25519 da RFC 8032 (so para teste: lento e sem cuidado com tempo constante)."""
    a, prefixo = _expandir(segredo)
    q = assinatura._Q
    publica = _comprimir(assinatura._multiplica(a, assinatura._BASE))
    r = int.from_bytes(hashlib.sha512(prefixo + mensagem).digest(), "little") % q
    r_bytes = _comprimir(assinatura._multiplica(r, assinatura._BASE))
    h = int.from_bytes(hashlib.sha512(r_bytes + publica + mensagem).digest(), "little") % q
    return r_bytes + ((r + h * a) % q).to_bytes(32, "little")


def b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def pacote(chave: str, maquina: str, produtos, *, cliente: str = "Cliente de Teste",
           tipo: str = "vitalicia", expira_em=None, max_computadores: int = 1,
           computador: str = COMPUTADOR, dias_offline: int = 30, **mudancas) -> dict:
    """O que a Edge Function devolve em `assinado`."""
    agora = datetime.now(timezone.utc)
    conteudo = {
        "v": 1, "kid": KID, "chave": chave, "maquina": maquina, "computador": computador,
        "cliente": cliente, "tipo": tipo, "produtos": [str(p).upper() for p in produtos],
        "expira_em": expira_em, "max_computadores": max_computadores,
        "emitida_em": agora.isoformat(), "valida_ate": (agora + timedelta(days=dias_offline)).isoformat(),
    }
    conteudo.update(mudancas)
    bruto = json.dumps(conteudo, ensure_ascii=False).encode("utf-8")
    return {"v": 1, "kid": KID, "licenca": b64(bruto), "assinatura": b64(assinar(bruto))}


def pacote_pix(pix: str, *, computador: str = COMPUTADOR, uso: str = "pagamentos",
               chave: str = "7K4M-9QX2-BT5H-3DWZ", maquina: str = "AAAA-BBBB") -> dict:
    """A chave Pix assinada que a Edge Function `pagamentos` devolve."""
    conteudo = {"v": 1, "kid": KID, "uso": uso, "chave": chave, "maquina": maquina,
                "computador": computador, "pix_chave": pix,
                "emitido_em": datetime.now(timezone.utc).isoformat()}
    bruto = json.dumps(conteudo, ensure_ascii=False).encode("utf-8")
    return {"v": 1, "kid": KID, "licenca": b64(bruto), "assinatura": b64(assinar(bruto))}


def pacote_atualizacao(versao: str, url: str, sha256: str = "", *, notas: str = "",
                       obrigatoria: bool = False, automatica: bool = True,
                       tamanho: int = 0, uso: str = "atualizacao", **mudancas) -> dict:
    """O manifesto assinado que a Edge Function `versao` devolve."""
    conteudo = {"v": 1, "kid": KID, "uso": uso, "versao": versao, "url": url,
                "sha256": sha256, "notas": notas, "tamanho": tamanho,
                "obrigatoria": obrigatoria, "automatica": automatica,
                "emitido_em": datetime.now(timezone.utc).isoformat()}
    conteudo.update(mudancas)
    bruto = json.dumps(conteudo, ensure_ascii=False).encode("utf-8")
    return {"v": 1, "kid": KID, "licenca": b64(bruto), "assinatura": b64(assinar(bruto))}


def assinar_licenca(licenca):
    """Devolve a mesma License, agora com o pacote assinado dentro."""
    from dataclasses import replace

    return replace(licenca, assinado=pacote(
        licenca.key, licenca.machine, licenca.entitlements, cliente=licenca.customer,
        tipo=licenca.tipo or "vitalicia", expira_em=licenca.expires_at,
        max_computadores=licenca.max_machines))


@contextlib.contextmanager
def licenca_de_teste(computador: str = COMPUTADOR):
    """O Hub confia na chave de teste e se reconhece como `computador`."""
    with mock.patch.dict(assinatura.CHAVES_PUBLICAS, {KID: publica_de().hex()}), \
         mock.patch.object(assinatura, "computador_id", return_value=computador):
        yield
