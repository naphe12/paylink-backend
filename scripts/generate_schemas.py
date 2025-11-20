import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # backend/
MODELS_DIR = os.path.join(BASE_DIR, "app", "models")
SCHEMAS_DIR = os.path.join(BASE_DIR, "app", "schemas")

os.makedirs(SCHEMAS_DIR, exist_ok=True)

print("🧩 Génération automatique des schémas Pydantic depuis les modèles SQLAlchemy...")

# Parcourir tous les fichiers modèles
for file in os.listdir(MODELS_DIR):
    if not file.endswith(".py") or file.startswith("_") or file.startswith("__"):
        continue

    model_name = file.replace(".py", "")
    schema_name = model_name.capitalize()
    input_path = os.path.join(MODELS_DIR, file)
    output_path = os.path.join(SCHEMAS_DIR, file)

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extraire le nom de la classe principale du modèle
    match = re.search(r"class\s+(\w+)\(Base\):", content)
    if not match:
        continue

    class_name = match.group(1)
    print(f"📘 Modèle détecté : {class_name}")

    # Génération du contenu Pydantic
    schema_code = f"""# Auto-generated from {file}
import uuid
import decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# 🔹 Base
class {class_name}Base(BaseModel):
    pass

# 🔹 Création
class {class_name}Create({class_name}Base):
    pass

# 🔹 Mise à jour
class {class_name}Update(BaseModel):
    pass

# 🔹 Lecture / Réponse
class {class_name}Read({class_name}Base):
    id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(schema_code)

print("\n✅ Tous les fichiers de schémas ont été générés dans app/schemas/")
