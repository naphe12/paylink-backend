import os
import re

# 🧭 Répertoires
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # backend/
MODELS_DIR = os.path.join(BASE_DIR, "app", "models")
INPUT_FILE = os.path.join(MODELS_DIR, "_generated_all.py")

os.makedirs(MODELS_DIR, exist_ok=True)

print(f"📄 Lecture : {INPUT_FILE}")

# 🧠 Lire le fichier brut
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 🔍 Extraire les classes SQLAlchemy
pattern = re.compile(r"(class\s+\w+\(Base\):[\s\S]*?)(?=^class\s|\Z)", re.MULTILINE)
matches = pattern.findall(content)

if not matches:
    print("❌ Aucune classe trouvée dans _generated_all.py")
    exit()

# 💡 Entête standard pour SQLAlchemy 2.0 style
header = """# Auto-generated from database schema
import uuid
from typing import Optional, List

from sqlalchemy import *
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.core.database import Base

"""

# ✂️ Découper chaque classe
for match in matches:
    class_name = re.search(r"class\s+(\w+)\(Base\):", match).group(1)
    filename = f"{class_name.lower()}.py"
    path = os.path.join(MODELS_DIR, filename)

    with open(path, "w", encoding="utf-8") as out:
        out.write(header)
        out.write(match.strip() + "\n")

    print(f"✅ Modèle généré : {filename}")

print("\n🎉 Tous les modèles ont été séparés avec succès !")
