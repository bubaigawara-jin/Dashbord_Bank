"""
02_fraud_rules.py
------------------
Etape 2 du pipeline BI : detection de fraude par regles metier.

IMPORTANT : ce dataset synthetique ne contient PAS de colonne "is_fraud"
dans transactions.csv (contrairement a ce que suggere le readme source).
On construit donc un score de risque (0-100) et un flag "is_suspected_fraud"
a partir de regles classiques utilisees en detection de fraude bancaire :

  R1 - Montant aberrant : transaction > moyenne + 3 ecarts-types du compte
  R2 - Transaction nocturne (22h-6h) sur montant eleve (> P90 global)
  R3 - Auto-transfert (compte origine == compte destination)
  R4 - Rafale de transactions : > 5 transactions du meme compte origine
       en moins de 60 minutes
  R5 - Montant proche/depassant le solde du compte (vidage de compte)
  R6 - Transaction sur un compte avec statut "Inactive"/"Closed"

Chaque regle declenchee ajoute des points au score. Un score >= 50 marque
la transaction comme suspecte (is_suspected_fraud = 1).

Usage :
    python 02_fraud_rules.py   (a executer apres 01_clean_data.py)
"""

from pathlib import Path

import pandas as pd
import numpy as np

from db_connection import get_engine

BASE_DIR = Path(__file__).resolve().parent.parent
CLEAN_DIR = BASE_DIR / "data" / "clean"
DOCS_DIR = BASE_DIR / "docs"

engine = get_engine()
transactions = pd.read_sql("SELECT * FROM transactions", engine, parse_dates=["TransactionDate"])
accounts = pd.read_sql("SELECT * FROM accounts", engine)
account_statuses = pd.read_sql("SELECT * FROM account_statuses", engine)

print("=" * 70)
print("SCORING DE FRAUDE - Regles metier")
print("=" * 70)
print(f"Transactions chargees : {len(transactions)}")

# ------------------------------------------------------------------
# Stats par compte origine (moyenne / ecart-type des montants)
# ------------------------------------------------------------------
stats = (
    transactions.groupby("AccountOriginID")["Amount"]
    .agg(["mean", "std", "count"])
    .rename(columns={"mean": "acc_mean", "std": "acc_std", "count": "acc_count"})
)
transactions = transactions.merge(stats, left_on="AccountOriginID", right_index=True, how="left")
transactions["acc_std"] = transactions["acc_std"].fillna(0)

p90_amount = transactions["Amount"].quantile(0.90)

# ------------------------------------------------------------------
# R1 - Montant aberrant (> moyenne + 3 sigma du compte, avec au moins 5 tx d'historique)
# ------------------------------------------------------------------
transactions["rule_R1_amount_outlier"] = (
    (transactions["acc_count"] >= 5)
    & (transactions["Amount"] > transactions["acc_mean"] + 3 * transactions["acc_std"])
)

# ------------------------------------------------------------------
# R2 - Transaction nocturne + montant eleve
# ------------------------------------------------------------------
transactions["rule_R2_night_high_amount"] = transactions["is_night"].astype(bool) & (
    transactions["Amount"] > p90_amount
)

# ------------------------------------------------------------------
# R3 - Auto-transfert
# ------------------------------------------------------------------
transactions["rule_R3_self_transfer"] = transactions["is_self_transfer"].astype(bool)

# ------------------------------------------------------------------
# R4 - Rafale de transactions (> 5 en moins de 60 min sur le meme compte origine)
# ------------------------------------------------------------------
transactions = transactions.sort_values(["AccountOriginID", "TransactionDate"])
transactions["prev_time"] = transactions.groupby("AccountOriginID")["TransactionDate"].shift(1)
transactions["gap_minutes"] = (
    (transactions["TransactionDate"] - transactions["prev_time"]).dt.total_seconds() / 60
)
# Compte du nombre de transactions du compte dans la fenetre glissante de 60 min precedente
transactions["rule_R4_burst"] = False
for acc_id, grp in transactions.groupby("AccountOriginID"):
    times = grp["TransactionDate"].values
    idx = grp.index
    counts = np.zeros(len(grp), dtype=int)
    j = 0
    for i in range(len(grp)):
        while times[i] - times[j] > np.timedelta64(60, "m"):
            j += 1
        counts[i] = i - j + 1
    transactions.loc[idx, "rule_R4_burst"] = counts > 5

# ------------------------------------------------------------------
# R5 - Montant proche/depassant le solde actuel du compte origine
# ------------------------------------------------------------------
acc_balance = accounts.set_index("AccountID")["Balance"]
transactions["origin_balance"] = transactions["AccountOriginID"].map(acc_balance)
transactions["rule_R5_drains_balance"] = (
    transactions["origin_balance"].notna()
    & (transactions["Amount"] >= 0.9 * transactions["origin_balance"])
    & (transactions["origin_balance"] > 0)
)

# ------------------------------------------------------------------
# R6 - Compte origine inactif/ferme au moment de la transaction
# ------------------------------------------------------------------
inactive_status_ids = set(
    account_statuses.loc[
        account_statuses["StatusName"].str.contains("Inactive|Closed", case=False, na=False),
        "AccountStatusID",
    ]
)
acc_status = accounts.set_index("AccountID")["AccountStatusID"]
transactions["origin_status_id"] = transactions["AccountOriginID"].map(acc_status)
transactions["rule_R6_inactive_account"] = transactions["origin_status_id"].isin(inactive_status_ids)

# ------------------------------------------------------------------
# Score final (ponderation simple, transparente et ajustable)
# ------------------------------------------------------------------
WEIGHTS = {
    "rule_R1_amount_outlier": 25,
    "rule_R2_night_high_amount": 15,
    "rule_R3_self_transfer": 15,
    "rule_R4_burst": 20,
    "rule_R5_drains_balance": 20,
    "rule_R6_inactive_account": 25,
}

transactions["fraud_risk_score"] = 0
for rule, weight in WEIGHTS.items():
    transactions["fraud_risk_score"] += transactions[rule].astype(int) * weight

transactions["fraud_risk_score"] = transactions["fraud_risk_score"].clip(upper=100)
transactions["is_suspected_fraud"] = (transactions["fraud_risk_score"] >= 50).astype(int)

n_flagged = transactions["is_suspected_fraud"].sum()
pct_flagged = 100 * n_flagged / len(transactions)
print(f"\nTransactions suspectes (score >= 50) : {n_flagged} ({pct_flagged:.2f}%)")
for rule in WEIGHTS:
    print(f"  {rule}: {transactions[rule].sum()} occurrences")

# ------------------------------------------------------------------
# Nettoyage des colonnes techniques et sauvegarde
# ------------------------------------------------------------------
transactions = transactions.drop(columns=["prev_time", "gap_minutes", "acc_mean", "acc_std", "acc_count"])

out_csv = CLEAN_DIR / "transactions_flagged.csv"
transactions.to_csv(out_csv, index=False)
print(f"\nExport : {out_csv}")

with engine.begin() as conn:
    transactions.to_sql("transactions_flagged", conn, index=False, if_exists="replace")
print("Table 'transactions_flagged' ecrite dans MySQL (base 'bi_fraude')")
print("\nTermine. La base MySQL 'bi_fraude' est prete pour SQL et Power BI.")
