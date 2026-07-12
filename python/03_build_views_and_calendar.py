"""
03_build_views_and_calendar.py
--------------------------------
Etape 3 du pipeline BI :
  1. Applique les vues SQL (sql/03_views.sql) a la base MySQL 'bi_fraude',
     pretes a etre consommees par Power BI.
  2. Genere une table calendrier "dim_date" (une ligne par jour, du
     premier au dernier jour couvert par les transactions) et l'exporte
     en CSV + dans la base. Tres utile pour les relations de dates et
     le "time intelligence" en DAX (Power BI).

Usage :
    python 03_build_views_and_calendar.py   (apres 01 et 02)
"""

from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db_connection import get_engine

BASE_DIR = Path(__file__).resolve().parent.parent
CLEAN_DIR = BASE_DIR / "data" / "clean"
SQL_DIR = BASE_DIR / "sql"

print("=" * 70)
print("CONSTRUCTION DES VUES SQL + TABLE CALENDRIER (dim_date)")
print("=" * 70)

engine = get_engine()

# ------------------------------------------------------------------
# 1. Appliquer les vues
# ------------------------------------------------------------------
views_sql = (SQL_DIR / "03_views.sql").read_text()
statements = [s.strip() for s in views_sql.split(";") if s.strip()]
n_views = 0
with engine.begin() as conn:
    for stmt in statements:
        lines = [l for l in stmt.split("\n") if not l.strip().startswith("--")]
        clean_stmt = "\n".join(lines).strip()
        if not clean_stmt:
            continue
        conn.execute(text(clean_stmt))
        if clean_stmt.upper().startswith("CREATE") and "VIEW" in clean_stmt.upper():
            n_views += 1
print(f"  {n_views} vues creees/mises a jour.")

# ------------------------------------------------------------------
# 2. Table calendrier dim_date
# ------------------------------------------------------------------
with engine.connect() as conn:
    min_max = conn.execute(
        text("SELECT MIN(TransactionDate), MAX(TransactionDate) FROM transactions WHERE TransactionDate IS NOT NULL")
    ).fetchone()
start_date = pd.to_datetime(min_max[0]).normalize()
end_date = pd.to_datetime(min_max[1]).normalize()

print(f"  Periode couverte : {start_date.date()} -> {end_date.date()}")

dates = pd.date_range(start_date, end_date, freq="D")
dim_date = pd.DataFrame({"DateKey": dates})
dim_date["Year"] = dim_date["DateKey"].dt.year
dim_date["Month"] = dim_date["DateKey"].dt.month
dim_date["MonthName"] = dim_date["DateKey"].dt.strftime("%B")
dim_date["Day"] = dim_date["DateKey"].dt.day
dim_date["DayOfWeek"] = dim_date["DateKey"].dt.dayofweek
dim_date["DayName"] = dim_date["DateKey"].dt.strftime("%A")
dim_date["Quarter"] = dim_date["DateKey"].dt.quarter
dim_date["IsWeekend"] = dim_date["DayOfWeek"].isin([5, 6])
dim_date["AnneeMois"] = dim_date["DateKey"].dt.strftime("%Y-%m")

with engine.begin() as conn:
    dim_date.to_sql("dim_date", conn, index=False, if_exists="replace")
dim_date.to_csv(CLEAN_DIR / "dim_date.csv", index=False)
print(f"  Table dim_date creee : {len(dim_date)} jours.")

# ------------------------------------------------------------------
# 3. Export CSV de chaque vue (pour Power BI "Import CSV" sans pilote MySQL)
# ------------------------------------------------------------------
print("\n--- Export CSV des vues (data/clean/) ---")
view_names = [
    "vw_fact_transactions",
    "vw_dim_customer_360",
    "vw_dim_account",
    "vw_fact_loans",
    "vw_kpi_monthly_summary",
    "vw_fraud_summary",
]
for v in view_names:
    df = pd.read_sql(f"SELECT * FROM {v}", engine)
    out_path = CLEAN_DIR / f"{v}.csv"
    df.to_csv(out_path, index=False)
    print(f"  -> {out_path.name} ({len(df)} lignes)")

print("\nTermine. La base MySQL 'bi_fraude' contient maintenant les tables,")
print("les vues et la table calendrier pretes pour Power BI.")
