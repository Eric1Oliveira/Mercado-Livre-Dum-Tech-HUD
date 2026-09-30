"""Atalho para rodar o DumTech Hub durante o desenvolvimento.

    python run_hub.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dumtech.main import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
