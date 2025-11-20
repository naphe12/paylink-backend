import importlib.util
import inspect
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # backend/
APP_DIR = os.path.join(BASE_DIR, "app")
MODELS_DIR = os.path.join(APP_DIR, "models")
SCHEMAS_DIR = os.path.join(APP_DIR, "schemas")

os.makedirs(SCHEMAS_DIR, exist_ok=True)

# Assurer que app/ est importable
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, APP_DIR)

print("🧩 Génération automatique des schémas Pydantic à partir des modèles SQLAlchemy...")

# Importer tous les fichiers modèles dynamiquement
for file in os.listdir(MODELS_DIR):
    if not file.endswith(".py") or file.startswith("_") or file.startswith("__"):
        continue

    module_name = f"app.models.{file[:-3]}"
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        continue

    module = importlib.import_module(module_name)

    # Récupérer toutes les classes SQLAlchemy (héritant de Base)
    for name, cls in inspect.getmembers(module, inspect.isclass):
        if hasattr(cls, "__tablename__") and hasattr(cls, "__table__"):
            print(f"📘 Modèle détecté : {name}")
            fields = []
            imports = set()

            # Parcourir les colonnes SQLAlchemy
            for column in cls.__table__.columns:
                col_name = column.name
                col_type = str(column.type).lower()
                is_nullable = column.nullable
                default = column.default
                py_type = "str"  # valeur par défaut

                # Détection du type Python
                if "uuid" in col_type:
                    py_type = "uuid.UUID"
                    imports.add("import uuid")
                elif "numeric" in col_type or "decimal" in col_type:
                    py_type = "decimal.Decimal"
                    imports.add("import decimal")
                elif "int" in col_type:
                    py_type = "int"
                elif "bool" in col_type:
                    py_type = "bool"
                elif "date" in col_type:
                    py_type = "datetime"
                    imports.add("from datetime import datetime")
                elif "json" in col_type:
                    py_type = "dict"
                elif "char" in col_type or "text" in col_type or "citext" in col_type:
                    py_type = "str"
                elif "float" in col_type:
                    py_type = "float"

                # Déterminer si le champ est optionnel
                if is_nullable or default is not None:
                    py_type = f"Optional[{py_type}]"

                fields.append(f"    {col_name}: {py_type}")

            # Créer le contenu du schema Pydantic
            schema_lines = [
                "# Auto-generated from SQLAlchemy model",
                *sorted(list(imports)),
                "from typing import Optional",
                "from pydantic import BaseModel, Field",
                "",
                f"class {name}Base(BaseModel):",
                *(fields if fields else ["    pass"]),
                "",
                f"class {name}Create({name}Base):",
                "    pass",
                "",
                f"class {name}Update(BaseModel):",
                *(f"    {f.split(':')[0]}: Optional{f.split(':')[1]}" for f in fields),
                "",
                f"class {name}Read({name}Base):",
                "    class Config:",
                "        from_attributes = True",
            ]

            output_path = os.path.join(SCHEMAS_DIR, f"{name.lower()}.py")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(schema_lines))

print("\n✅ Tous les schémas Pydantic ont été générés dans app/schemas/")
