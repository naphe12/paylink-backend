import os
import pickle
from typing import Any, Dict

from app.config import settings

_model = None


def load_model():
    global _model
    if _model is not None:
        return _model
    if not settings.ML_SCORING_ENABLED:
        return None
    if not os.path.exists(settings.ML_MODEL_PATH):
        return None
    with open(settings.ML_MODEL_PATH, "rb") as f:
        _model = pickle.load(f)
    return _model


def predict_score(features: Dict[str, Any]) -> int:
    """
    Expected model API:
      - predict_proba([vector]) -> [.., fraud_prob]
      - or predict([vector]) -> direct score/class
    Returns -1 when model is disabled/unavailable.
    """
    model = load_model()
    if not model:
        return -1

    vector = [
        float(features.get("amount_bif", 0)),
        float(features.get("user_age_days", 0)),
        float(features.get("trades_24h", 0)),
        float(features.get("price_deviation", 0)),
        float(features.get("kyc_verified", 0)),
    ]

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba([vector])[0][1]
        return int(max(0, min(100, round(proba * 100))))
    pred = model.predict([vector])[0]
    return int(max(0, min(100, pred)))
