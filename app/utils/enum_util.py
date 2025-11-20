from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

def cast_enum(value, enum_class, name: str, schema: str = None):
    """
    Caste une valeur ENUM vers le type PostgreSQL ENUM avec schéma.
    
    :param value: La valeur à caster (ex: ContributionStatus.paid)
    :param enum_class: La classe Python Enum (ex: ContributionStatus)
    :param name: Le nom du type ENUM dans PostgreSQL
    :param schema: Le schéma PostgreSQL (ex: "paylink")
    :return: Une expression SQLAlchemy castée
    """
    enum_type = PG_ENUM(enum_class, name=name, schema=schema, create_type=False)
    return cast(value, enum_type)

