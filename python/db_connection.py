"""
db_connection.py
------------------
Point de connexion unique a MySQL, utilise par 01_clean_data.py,
02_fraud_rules.py et 03_build_views_and_calendar.py.

On utilise SQLAlchemy (plutot que mysql-connector directement) car
pandas.to_sql() / pandas.read_sql() en ont besoin en interne pour parler
a MySQL, et ca permet de changer de SGBD plus tard (PostgreSQL, etc.)
en changeant uniquement la ligne CONNECTION_STRING.

Configuration : variables d'environnement (a definir avant de lancer les
scripts, ou dans un fichier .env charge par votre shell) :

    export DB_HOST=localhost
    export DB_PORT=3306
    export DB_USER=root
    export DB_PASSWORD=motdepasse
    export DB_NAME=bi_fraude

Si une variable n'est pas definie, une valeur par defaut raisonnable
pour un environnement local est utilisee (voir ci-dessous).
"""

import os
from sqlalchemy import create_engine

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "bi_fraude")

# pymysql est le driver Python pur pour MySQL (pas de dependance systeme
# a compiler, contrairement a mysqlclient) - suffisant pour ce projet.
CONNECTION_STRING = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?charset=utf8mb4"
)


def get_engine():
    """Retourne un moteur SQLAlchemy connecte a la base MySQL 'bi_fraude'.

    Prerequis : la base doit deja exister cote serveur, car MySQL
    (contrairement a SQLite) ne cree pas une base toute seule.
    Executez d'abord, une seule fois :
        mysql -u root -p -e "CREATE DATABASE bi_fraude CHARACTER SET utf8mb4;"
    """
    return create_engine(CONNECTION_STRING)
