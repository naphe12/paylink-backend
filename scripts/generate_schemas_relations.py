import importlib.util
import inspect
import os
import sys

from sqlalchemy.orm import DeclarativeMeta

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # backend/
APP_DIR = os.path.join(BASE_DIR, "app")
MODELS_DIR = os.path.join(APP_DIR, "models")
SCHEMAS_DIR = os.path.join(APP_DIR, "schemas")

os.makedirs(SCHEMAS_DIR, exist_ok=True)
sys.path.insert(0, APP_DIR)
sys.path.insert(0, BASE_DIR)

print("🧠 Génération intelligente des schémas Pydantic (avec relations)...")

def detect_python_type(col_type: str):
    """Associer un type SQLAlchemy à un type Python"""
    t = col_type.lower()
    if "uuid" in t:
        return "uuid.UUID", "import uuid"
    elif "decimal" in t or "numeric" in t:
        return "decimal.Decimal", "import decimal"
    elif "int" in t:
        return "int", None
    elif "bool" in t:
        return "bool", None
    elif "date" in t:
        return "datetime", "from datetime import datetime"
    elif "json" in t:
        return "dict", None
    elif "char" in t or "text" in t or "citext" in t:
        return "str", None
    elif "float" in t:
        return "float", None
    return "str", None


for file in os.listdir(MODELS_DIR):
    if not file.endswith(".py") or file.startswith("_"):
        continue

    module_name = f"app.models.{file[:-3]}"
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        continue

    module = importlib.import_module(module_name)

    for name, cls in inspect.getmembers(module, inspect.isclass):
        if not hasattr(cls, "__table__") or not isinstance(cls, DeclarativeMeta):
            continue

        print(f"📘 Traitement du modèle : {name}")
        imports = set(["from pydantic import BaseModel, Field", "from typing import Optional"])
        fields = []
        rels = []

        # Parcours des colonnes
        for column in cls.__table__.columns:
            col_type = str(column.type)
            py_type, imp = detect_python_type(col_type)
            if imp:
                imports.add(imp)

            # ignorer pour Create
            auto_fields = ["id", "created_at", "updated_at"]
            nullable = column.nullable or column.default is not None

            typ = f"Optional[{py_type}]" if nullable else py_type
            fields.append((column.name, typ, col_type))
        
        # Relations SQLAlchemy
        for rel_name, rel_prop in cls.__mapper__.relationships.items():
            target = rel_prop.mapper.class_.__name__
            if rel_prop.uselist:
                rels.append((rel_name, f"list[{target}Read]"))
            else:
                rels.append((rel_name, f"Optional[{target}Read]"))

        # Construire le contenu du schéma
        base_lines = [f"    {n}: {t}" for n, t, _ in fields]
        update_lines = [f"    {n}: Optional[{t}]" for n, t, _ in fields]
        create_lines = [f"    {n}: {t}" for n, t, _ in fields if n not in ["id", "created_at", "updated_at"]]
        read_lines = base_lines + [f"    {r}: {t} = None" for r, t in rels]

        schema = [
            "# Auto-generated from SQLAlchemy model with relationships",
            *sorted(imports),
            "",
            f"class {name}Base(BaseModel):",
            *(base_lines if base_lines else ["    pass"]),
            "",
            f"class {name}Create({name}Base):",
            *(create_lines if create_lines else ["    pass"]),
            "",
            f"class {name}Update(BaseModel):",
            *(update_lines if update_lines else ["    pass"]),
            "",
            f"class {name}Read({name}Base):",
            *(read_lines if read_lines else ["    pass"]),
            "    class Config:",
            "        from_attributes = True",
            "",
        ]

        output_file = os.path.join(SCHEMAS_DIR, f"{name.lower()}.py")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(schema))

print("\n✅ Schémas enrichis générés dans app/schemas/")
