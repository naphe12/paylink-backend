# fix_circular_imports.py
import re
from pathlib import Path

SCHEMAS_DIR = Path("app/schemas")
MODEL_NAMES = set()

TYPE_CHECKING_BLOCK = """\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"""

def ensure_future_import(content: str) -> str:
    """Ajoute 'from __future__ import annotations' en haut du fichier si absent."""
    if "from __future__ import annotations" not in content:
        lines = content.splitlines()
        insert_at = 0
        while insert_at < len(lines) and lines[insert_at].strip().startswith(("#!", "#", '"""', "'''")):
            insert_at += 1
        lines.insert(insert_at, "from __future__ import annotations")
        content = "\n".join(lines)
    return content


def add_forward_references(content: str) -> str:
    """Transforme Optional[ClassNameRead] → Optional["ClassNameRead"]"""
    pattern = r"Optional\[(\w+Read)\]"
    return re.sub(pattern, r'Optional["\1"]', content)


def fix_file(path: Path):
    global MODEL_NAMES
    content = path.read_text(encoding="utf-8")
    original_content = content

    if "__init__" in path.name or "fix_circular_imports" in path.name:
        return

    # 1️⃣ Ajout du future import
    content = ensure_future_import(content)

    # 2️⃣ Conversion en forward refs
    content = add_forward_references(content)

    # 3️⃣ Correction des imports internes
    internal_imports = re.findall(r"from\s+\.(\w+)\s+import\s+(\w+)", content)
    if not internal_imports:
        if content != original_content:
            path.write_text(content, encoding="utf-8")
        return

    print(f"🛠️ Corrige {path.name} → {len(internal_imports)} import(s) internes")

    new_imports = []
    for module, cls in internal_imports:
        pattern = rf"from\s+\.{module}\s+import\s+{cls}"
        content = re.sub(pattern, "", content)
        new_imports.append(f"    from app.schemas.{module} import {cls}\n")
        MODEL_NAMES.add(cls)

    if "TYPE_CHECKING" not in content:
        content = TYPE_CHECKING_BLOCK + "".join(new_imports) + "\n" + content
    else:
        content = re.sub(
            r"(if TYPE_CHECKING:\n)",
            r"\1" + "".join(new_imports),
            content,
        )

    path.write_text(content.strip() + "\n", encoding="utf-8")


def update_init_file():
    """Ajoute les .model_rebuild() dans app/schemas/__init__.py"""
    init_path = SCHEMAS_DIR / "__init__.py"

    # ✅ Crée le fichier si nécessaire
    if not init_path.exists():
        print("⚙️  Création de app/schemas/__init__.py ...")
        init_path.parent.mkdir(parents=True, exist_ok=True)
        init_path.write_text("# Auto-generated __init__.py\n", encoding="utf-8")

    content = init_path.read_text(encoding="utf-8")

    rebuild_block = "\n\n# 🔄 Reconstruit tous les modèles après import\n"
    for name in sorted(MODEL_NAMES):
        rebuild_block += (
            f"try:\n"
            f"    from app.schemas import {name.split('Read')[0].lower()}, {name}\n"
            f"    {name}.model_rebuild()\n"
            f"except Exception:\n"
            f"    pass\n"
        )

    if "# 🔄 Reconstruit tous les modèles" not in content:
        content += rebuild_block
    else:
        content = re.sub(r"# 🔄 Reconstruit.*", rebuild_block, content, flags=re.S)

    init_path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"✅ __init__.py mis à jour avec {len(MODEL_NAMES)} rebuilds.")


def main():
    if not SCHEMAS_DIR.exists():
        raise FileNotFoundError(f"❌ Le dossier {SCHEMAS_DIR} n'existe pas !")

    print("🔍 Scan du dossier schemas...")
    for py_file in SCHEMAS_DIR.glob("*.py"):
        fix_file(py_file)
    update_init_file()
    print("✅ Correction automatique terminée.")


if __name__ == "__main__":
    main()
