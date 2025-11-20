# app/utils/responses.py
from fastapi.responses import JSONResponse


def success(data=None, message="Opération réussie ✅", status_code=200):
    """Retourne une réponse API standardisée."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "message": message,
            "data": data or {},
        },
    )

def error(message="Erreur serveur ❌", status_code=400):
    """Retourne une erreur API standardisée."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
        },
    )

def paginated(data, page: int, per_page: int, total: int):
    """Retourne un format paginé propre."""
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "data": data,
    }
