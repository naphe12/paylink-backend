"""
Quick mapper configuration check.

Usage:
  PYTHONPATH=backend python backend/scripts/check_mappers.py
  (On PowerShell)
  $env:PYTHONPATH='backend'; python backend/scripts/check_mappers.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import pkgutil
import importlib


def _ensure_sys_path() -> None:
    # Ensure the parent of the 'app' package (i.e., the backend folder) is on sys.path
    here = Path(__file__).resolve()
    backend_dir = here.parents[1]  # backend/
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def main() -> int:
    _ensure_sys_path()
    try:
        from sqlalchemy.orm import configure_mappers  # type: ignore
    except Exception as exc:  # pragma: no cover
        print("ERROR: SQLAlchemy not available:", exc)
        return 2

    try:
        # Import all submodules under app.models
        models_pkg = importlib.import_module("app.models")
        skip = {
            # Skip known duplicate/experimental modules that conflict with canonical models
            "app.models.amlevents1",
        }
        for _, modname, _ in pkgutil.iter_modules(models_pkg.__path__, models_pkg.__name__ + "."):
            if modname in skip:
                continue
            importlib.import_module(modname)

        # Configure mappers to surface relationship/back_populates issues
        configure_mappers()
    except Exception as exc:
        import traceback
        print("Mapper configuration FAILED:")
        print(exc)
        traceback.print_exc()
        return 1

    print("OK: mappers configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
