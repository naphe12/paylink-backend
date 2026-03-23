import httpx

from app.core.config import settings


def _normalize_currency_code(value: str | None, fallback: str | None = None) -> str:
    raw = str(value or fallback or "").strip().upper()
    aliases = {
        "CFA": "XOF",
        "FCFA": "XAF",
    }
    return aliases.get(raw, raw[:3])


async def get_open_exchange_rate_to_eur(origin: str) -> float | None:
    origin = _normalize_currency_code(origin)
    if not origin:
        return None
    if origin == "EUR":
        return 1.0

    app_id = str(getattr(settings, "OPENEXCHANGERATES_APP_ID", "") or "").strip()
    if not app_id:
        return None

    url = "https://openexchangerates.org/api/latest.json"
    params = {
        "app_id": app_id,
        "symbols": f"EUR,{origin}",
        "prettyprint": "false",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()

    rates = data.get("rates") or {}
    eur_rate = rates.get("EUR")
    origin_rate = rates.get(origin)
    if eur_rate in (None, 0) or origin_rate in (None, 0):
        return None

    return float(eur_rate) / float(origin_rate)
