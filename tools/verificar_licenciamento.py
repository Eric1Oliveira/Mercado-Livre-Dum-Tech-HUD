"""Confere se o servidor de licencas (Supabase) esta pronto.

    python tools/verificar_licenciamento.py                 -> so testa a conexao
    python tools/verificar_licenciamento.py CHAVE-DA-LICENCA -> testa uma chave real

Nao grava nada no computador: e so um diagnostico para o suporte.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from dumtech.core.licensing import (  # noqa: E402
    LicenseError,
    SupabaseLicenseGateway,
    machine_id,
    normalize_key,
)
from dumtech.core.supabase import SupabaseClient  # noqa: E402

CHAVE_INEXISTENTE = "ZZZZ-ZZZZ-ZZZZ-ZZZZ"


def main() -> int:
    cliente = SupabaseClient()
    gateway = SupabaseLicenseGateway(cliente)
    maquina = machine_id()

    print("Servidor .....:", cliente.url)
    print("Computador ...:", maquina)
    print()

    print("1) Conexao e banco preparado...")
    try:
        gateway.fetch(CHAVE_INEXISTENTE, maquina)
        print("   ATENCAO: a chave de teste foi aceita (nao deveria existir).")
    except LicenseError as erro:
        if erro.codigo == "nao_encontrada":
            print("   OK - servidor respondendo e tabelas/funcoes no lugar.")
        elif erro.codigo == "sem_internet":
            print("   FALHOU - sem internet:", erro)
            return 1
        else:
            print("   FALHOU -", erro)
            print("   Aplique as migrations de supabase/migrations (supabase db push).")
            return 1

    chave = normalize_key(sys.argv[1]) if len(sys.argv) > 1 else ""
    if not chave:
        print()
        print("Tudo certo. Para testar uma chave real:")
        print("   python tools/verificar_licenciamento.py XXXX-XXXX-XXXX-XXXX")
        return 0

    print()
    print(f"2) Ativando a chave {chave} neste computador...")
    try:
        licenca = gateway.fetch(chave, maquina)
    except LicenseError as erro:
        print(f"   RECUSADA ({erro.codigo}): {erro}")
        return 1

    print("   OK - licenca valida")
    print("   Cliente .......:", licenca.customer)
    print("   Produtos ......:", ", ".join(licenca.entitlements) or "(nenhum)")
    print("   Tipo ..........:", licenca.tipo or "(servidor antigo)")
    print("   Validade ......:", licenca.expires_at or "sem prazo")
    print("   Computadores ..:", f"{licenca.used_machines} de {licenca.max_machines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
