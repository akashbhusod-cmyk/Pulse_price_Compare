from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pricepulse_compare import create_app
from pricepulse_compare.settings import AppSettings


app = create_app()


if __name__ == "__main__":
    settings = AppSettings()
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
