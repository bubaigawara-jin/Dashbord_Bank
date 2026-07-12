"""
01_clean_data.py
-----------------
Etape 1 du pipeline BI : nettoyage des donnees brutes (ETL).

Ce script :
  - charge les 11 fichiers CSV bruts (data/raw/)
  - corrige les problemes de qualite connus du dataset (~7% de bruit) :
        * valeurs manquantes (nulls)
        * doublons exacts
        * formats de dates incoherents / dates futures impossibles
        * espaces et casse incoherents dans le texte (typos, villes, noms...)
        * formats numeriques incoherents
        * IDs non sequentiels (on ne les "corrige" pas, on les garde comme cles)
  - exporte les tables nettoyees en CSV (data/clean/) et dans la base
    MySQL 'bi_fraude', prete pour les requetes SQL et pour Power BI
    (connecteur MySQL natif ou Import CSV).
  - genere un rapport qualite (docs/data_quality_report.csv)

Usage :
    python 01_clean_data.py
"""

from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

from db_connection import get_engine

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
CLEAN_DIR = BASE_DIR / "data" / "clean"
DOCS_DIR = BASE_DIR / "docs"

CLEAN_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

TODAY = pd.Timestamp(datetime.now().date())

quality_report_rows = []


def log_quality(table, issue, count):
    quality_report_rows.append({"table": table, "issue": issue, "count": int(count)})
    print(f"  [{table}] {issue}: {count}")


def clean_text_series(s: pd.Series) -> pd.Series:
    """Trim whitespace, collapse multiple spaces, keep NaN as NaN."""
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .replace({"nan": np.nan, "": np.nan, "None": np.nan})
    )


def parse_dates(s: pd.Series) -> pd.Series:
    """Parse dates robustly even with mixed formats (ISO, DD/MM/YYYY, MM-DD-YYYY...)."""
    parsed = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=False)
    return parsed


def load_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / name)


print("=" * 70)
print("NETTOYAGE DES DONNEES - Projet BI Fraude Bancaire")
print("=" * 70)

# ------------------------------------------------------------------
# 1. Tables de reference (dimensions simples) - peu ou pas de nettoyage
# ------------------------------------------------------------------
account_statuses = load_raw("account_statuses.csv")
account_types = load_raw("account_types.csv")
customer_types = load_raw("customer_types.csv")
loan_statuses = load_raw("loan_statuses.csv")
transaction_types = load_raw("transaction_types.csv")

# ------------------------------------------------------------------
# 2. addresses
# ------------------------------------------------------------------
print("\n--- addresses.csv ---")
addresses = load_raw("addresses.csv")
before = len(addresses)

for col in ["Street", "City", "Country"]:
    n_null = addresses[col].isna().sum()
    addresses[col] = clean_text_series(addresses[col])
    log_quality("addresses", f"nulls in {col} (conserves, marques 'Inconnu')", n_null)
    addresses[col] = addresses[col].fillna("Inconnu")
    # normalisation casse (Title Case) pour corriger les typos de casse
    addresses[col] = addresses[col].str.title()

dup = addresses.duplicated().sum()
addresses = addresses.drop_duplicates()
log_quality("addresses", "doublons exacts supprimes", dup)

# ------------------------------------------------------------------
# 3. branches
# ------------------------------------------------------------------
print("\n--- branches.csv ---")
branches = load_raw("branches.csv")
branches["BranchName"] = clean_text_series(branches["BranchName"])
dup = branches.duplicated().sum()
branches = branches.drop_duplicates()
log_quality("branches", "doublons exacts supprimes", dup)

# ------------------------------------------------------------------
# 4. customers
# ------------------------------------------------------------------
print("\n--- customers.csv ---")
customers = load_raw("customers.csv")

for col in ["FirstName", "LastName"]:
    n_null = customers[col].isna().sum()
    customers[col] = clean_text_series(customers[col])
    log_quality("customers", f"nulls in {col} (remplaces par 'Inconnu')", n_null)
    customers[col] = customers[col].fillna("Inconnu").str.title()

# Dates de naissance : formats mixtes -> ISO, dates futures = incoherentes
n_null_dob = customers["DateOfBirth"].isna().sum()
customers["DateOfBirth"] = parse_dates(customers["DateOfBirth"])
future_dob = (customers["DateOfBirth"] > TODAY).sum()
customers.loc[customers["DateOfBirth"] > TODAY, "DateOfBirth"] = pd.NaT
log_quality("customers", "dates de naissance futures invalidees", future_dob)
log_quality("customers", "dates de naissance non parsables/nulles", n_null_dob)

dup = customers.duplicated(subset=["CustomerID"]).sum()
customers = customers.drop_duplicates(subset=["CustomerID"], keep="first")
log_quality("customers", "doublons sur CustomerID supprimes", dup)

# ------------------------------------------------------------------
# 5. accounts
# ------------------------------------------------------------------
print("\n--- accounts.csv ---")
accounts = load_raw("accounts.csv")

n_null_open = accounts["OpeningDate"].isna().sum()
accounts["OpeningDate"] = parse_dates(accounts["OpeningDate"])
future_open = (accounts["OpeningDate"] > TODAY).sum()
accounts.loc[accounts["OpeningDate"] > TODAY, "OpeningDate"] = pd.NaT
log_quality("accounts", "dates d'ouverture futures invalidees", future_open)
log_quality("accounts", "dates d'ouverture non parsables/nulles", n_null_open)

# Balance : s'assurer que c'est bien numerique (formats inconsistants -> texte avec virgules etc.)
accounts["Balance"] = (
    accounts["Balance"].astype(str).str.replace(",", "", regex=False).astype(float)
)
neg_balance = (accounts["Balance"] < 0).sum()
log_quality("accounts", "comptes avec solde negatif (conserves, a surveiller)", neg_balance)

dup = accounts.duplicated(subset=["AccountID"]).sum()
accounts = accounts.drop_duplicates(subset=["AccountID"], keep="first")
log_quality("accounts", "doublons sur AccountID supprimes", dup)

# Integrite referentielle : comptes dont le CustomerID n'existe pas
orphan_acc = (~accounts["CustomerID"].isin(customers["CustomerID"])).sum()
log_quality("accounts", "comptes avec CustomerID orphelin (conserves, flag_orphelin)", orphan_acc)
accounts["is_orphan_customer"] = ~accounts["CustomerID"].isin(customers["CustomerID"])

# ------------------------------------------------------------------
# 6. loans
# ------------------------------------------------------------------
print("\n--- loans.csv ---")
loans = load_raw("loans.csv")

for col in ["StartDate", "EstimatedEndDate"]:
    n_null = loans[col].isna().sum()
    loans[col] = parse_dates(loans[col])
    log_quality("loans", f"{col} non parsables/nulles", n_null)

loans["PrincipalAmount"] = (
    loans["PrincipalAmount"].astype(str).str.replace(",", "", regex=False).astype(float)
)
loans["InterestRate"] = (
    loans["InterestRate"].astype(str).str.replace(",", "", regex=False).astype(float)
)

dup = loans.duplicated(subset=["LoanID"]).sum()
loans = loans.drop_duplicates(subset=["LoanID"], keep="first")
log_quality("loans", "doublons sur LoanID supprimes", dup)

orphan_loan = (~loans["AccountID"].isin(accounts["AccountID"])).sum()
log_quality("loans", "prets avec AccountID orphelin (conserves, flag_orphelin)", orphan_loan)
loans["is_orphan_account"] = ~loans["AccountID"].isin(accounts["AccountID"])

# ------------------------------------------------------------------
# 7. transactions (table la plus volumineuse : 50 000 lignes)
# ------------------------------------------------------------------
print("\n--- transactions.csv ---")
transactions = load_raw("transactions.csv")

n_null_date = transactions["TransactionDate"].isna().sum()
transactions["TransactionDate"] = parse_dates(transactions["TransactionDate"])
log_quality("transactions", "dates non parsables/nulles", n_null_date)

# Dates futures = anomalie connue du dataset (~1%) -> on les flague au lieu de les supprimer
transactions["is_future_date"] = transactions["TransactionDate"] > TODAY
log_quality("transactions", "transactions avec date future (flag_date_future)", transactions["is_future_date"].sum())

transactions["Amount"] = (
    transactions["Amount"].astype(str).str.replace(",", "", regex=False).astype(float)
)
neg_amount = (transactions["Amount"] < 0).sum()
log_quality("transactions", "montants negatifs (conserves, a verifier)", neg_amount)

transactions["Description"] = clean_text_series(transactions["Description"])

dup = transactions.duplicated(subset=["TransactionID"]).sum()
transactions = transactions.drop_duplicates(subset=["TransactionID"], keep="first")
log_quality("transactions", "doublons sur TransactionID supprimes", dup)

# Auto-transfert (Origin == Destination) : anomalie a surveiller pour la fraude
transactions["is_self_transfer"] = (
    transactions["AccountOriginID"] == transactions["AccountDestinationID"]
)
log_quality("transactions", "auto-transferts (Origin == Destination)", transactions["is_self_transfer"].sum())

# Integrite referentielle sur les comptes
valid_accounts = set(accounts["AccountID"])
transactions["origin_orphan"] = ~transactions["AccountOriginID"].isin(valid_accounts)
transactions["destination_orphan"] = ~transactions["AccountDestinationID"].isin(valid_accounts)
log_quality("transactions", "AccountOriginID orphelin", transactions["origin_orphan"].sum())
log_quality("transactions", "AccountDestinationID orphelin", transactions["destination_orphan"].sum())

# Colonnes utilitaires pour BI (annee/mois/heure/jour)
transactions["TransactionYear"] = transactions["TransactionDate"].dt.year
transactions["TransactionMonth"] = transactions["TransactionDate"].dt.month
transactions["TransactionHour"] = transactions["TransactionDate"].dt.hour
transactions["TransactionDOW"] = transactions["TransactionDate"].dt.dayofweek  # 0=lundi
transactions["is_weekend"] = transactions["TransactionDOW"].isin([5, 6])
transactions["is_night"] = transactions["TransactionHour"].apply(
    lambda h: (h >= 22 or h <= 5) if pd.notna(h) else False
)

# ------------------------------------------------------------------
# 8. Sauvegarde des tables nettoyees en CSV
# ------------------------------------------------------------------
print("\n--- Export CSV nettoye (data/clean/) ---")

clean_tables = {
    "account_statuses": account_statuses,
    "account_types": account_types,
    "customer_types": customer_types,
    "loan_statuses": loan_statuses,
    "transaction_types": transaction_types,
    "addresses": addresses,
    "branches": branches,
    "customers": customers,
    "accounts": accounts,
    "loans": loans,
    "transactions": transactions,
}

for name, df in clean_tables.items():
    out_path = CLEAN_DIR / f"{name}_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"  -> {out_path.name} ({len(df)} lignes)")

# ------------------------------------------------------------------
# 9. Chargement dans MySQL (pour SQL + Power BI)
# ------------------------------------------------------------------
print("\n--- Ecriture dans MySQL (base 'bi_fraude') ---")
engine = get_engine()

with engine.begin() as conn:
    for name, df in clean_tables.items():
        df.to_sql(name, conn, index=False, if_exists="replace")
        print(f"  table `{name}` ecrite ({len(df)} lignes)")

print("  Donnees chargees dans MySQL avec succes.")

# ------------------------------------------------------------------
# 10. Rapport qualite
# ------------------------------------------------------------------
report_df = pd.DataFrame(quality_report_rows)
report_path = DOCS_DIR / "data_quality_report.csv"
report_df.to_csv(report_path, index=False)
print(f"\nRapport qualite ecrit : {report_path}")
print("\nTermine. Lancer ensuite 02_fraud_rules.py")
