#!/bin/bash
set -e

echo "🧩 Génération des modèles SQLAlchemy depuis la base PostgreSQL..."
sqlacodegen postgresql+psycopg2://postgres:postgres@localhost:5432/paylinkdb \
  --schema paylink \
  --outfile backend/app/models/_generated_all_22.py

echo "✂️ Découpage des classes en fichiers individuels..."
#python backend/scripts/split_models.py

#echo "🔁 Mise à jour du __init__.py..."
#python backend/scripts/update_init_models.py

echo "✅ Tous les modèles sont prêts dans backend/app/models/"
