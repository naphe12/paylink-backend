"""App package bootstrap for legacy absolute imports.

This project contains imports like `from services...` and `from models...`.
When started as `uvicorn app.main:app`, Python resolves `app` from its parent
directory and does not automatically include the package directory itself on
`sys.path`. We add it explicitly so legacy imports keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

