import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("aerolink")

class LoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Infos de la requête
        method = request.method
        url = request.url.path
        client_ip = request.client.host

        logger.info(f"📥 Requête entrante: {method} {url} depuis {client_ip}")

        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"💥 Erreur pendant le traitement de {method} {url}")
            raise

        duration = round((time.time() - start_time) * 1000, 2)
        status_code = response.status_code

        logger.info(f"📤 Réponse: {method} {url} → {status_code} ({duration} ms)")
        logger.info(f"🔐 Headers de la requête: {dict(request.headers)}")
        return response