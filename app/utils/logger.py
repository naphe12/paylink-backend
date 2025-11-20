# app/utils/logger.py
import logging
from datetime import datetime

# Configuration de base
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("paylink")

def _colorize(msg, color):
    colors = {
        "blue": "\033[94m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "end": "\033[0m",
    }
    return f"{colors.get(color, '')}{msg}{colors['end']}"

def log_info(msg: str):
    """Log d'information (bleu)."""
    logger.info(_colorize(f"[{datetime.now():%H:%M:%S}] ℹ️ {msg}", "blue"))

def log_success(msg: str):
    """Log de succès (vert)."""
    logger.info(_colorize(f"[{datetime.now():%H:%M:%S}] ✅ {msg}", "green"))

def log_warning(msg: str):
    """Log d’avertissement (jaune)."""
    logger.warning(_colorize(f"[{datetime.now():%H:%M:%S}] ⚠️ {msg}", "yellow"))

def log_error(msg: str):
    """Log d’erreur (rouge)."""
    logger.error(_colorize(f"[{datetime.now():%H:%M:%S}] ❌ {msg}", "red"))
