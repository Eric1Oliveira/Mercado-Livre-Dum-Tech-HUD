"""Testes da plataforma DumTech.

Antes de qualquer import do projeto, a pasta de dados e desviada para um
diretorio temporario: os testes nunca tocam nos dados reais do usuario.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

PASTA_TESTE = Path(tempfile.mkdtemp(prefix="dumtech_tests_"))
os.environ["DUMTECH_DATA_DIR"] = str(PASTA_TESTE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Licenca local: os testes nunca acessam a internet nem o Supabase.
# Os testes de licenciamento usam gateways falsos proprios.
os.environ.setdefault("DUMTECH_LICENCA_LOCAL", "1")
