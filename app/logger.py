import logging
import os

# Crée le dossier logs s'il n'existe pas
os.makedirs("logs", exist_ok=True)

# Configure le logger racine (optionnel si tu veux centraliser)
logging.basicConfig(
    filename="logs/paylink_debug.log",
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    encoding="utf-8"
)

# Log de démarrage
#logging.info("Test de démarrage AeroLink")

# Fonction utilitaire pour récupérer un logger par nom
def get_logger(name="paylink"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.hasHandlers():
        handler = logging.FileHandler(f"logs/{name}.log", encoding="utf-8")
        formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
