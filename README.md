# Projet BI — Analyse Bancaire & Détection de Fraude

Projet complet **Python (nettoyage) → SQL (analyse) → Power BI (dashboard)**
construit à partir du dataset synthétique *"Synthetic Finance Dataset —
Customers, Accounts, Loans & Transactions"* (11 fichiers CSV, ~50 000 lignes,
~7% d'anomalies volontaires : nulls, doublons, dates incohérentes, etc.).

> ⚠️ Le dataset source ne contient **aucune colonne `is_fraud`** malgré ce
> qu'indique son readme d'origine. La détection de fraude est donc réalisée
> ici par un **moteur de règles métier** (score de risque 0-100), documenté
> dans `python/02_fraud_rules.py`.

---

## Structure du projet

```
bi_fraude/
├── README.md                        <- ce fichier
├── data/
│   ├── raw/                         <- 11 CSV originaux (non modifiés)
│   └── clean/                       <- sorties du pipeline (générées, pas versionnées à la main)
│       ├── *_clean.csv              <- chaque table nettoyée
│       ├── transactions_flagged.csv <- transactions + score de fraude
│       ├── dim_date.csv             <- table calendrier
│       └── vw_*.csv                 <- exports des vues, prêts pour Power BI
│       (les mêmes données vivent aussi dans la base MySQL 'bi_fraude')
├── python/
│   ├── requirements.txt
│   ├── db_connection.py             <- connexion MySQL partagée (config via variables d'env)
│   ├── 01_clean_data.py             <- nettoyage (nulls, doublons, dates, formats)
│   ├── 02_fraud_rules.py            <- scoring de fraude par règles métier
│   └── 03_build_views_and_calendar.py <- vues SQL + calendrier + exports CSV
├── sql/
│   ├── 00_create_schema.sql         <- DDL de référence (portage PostgreSQL/SQL Server)
│   ├── 02_kpi_queries.sql           <- 11 blocs de requêtes KPI bancaires
│   └── 03_views.sql                 <- vues consommées par Power BI
├── powerbi/
│   ├── README_PowerBI.md            <- guide pas-à-pas : import, modèle, pages
│   └── dax_measures.txt             <- mesures DAX prêtes à copier-coller
└── docs/
    ├── dataset_readme.md            <- readme original du dataset Kaggle
    └── data_quality_report.csv      <- rapport détaillé des anomalies corrigées
```

---

## Comment exécuter le pipeline

### 0. Créer la base MySQL (une seule fois)
```bash
mysql -u root -p -e "CREATE DATABASE bi_fraude CHARACTER SET utf8mb4;"
```

### 1. Configurer la connexion
Le script `python/db_connection.py` lit ses identifiants depuis des
variables d'environnement (valeurs par défaut : `localhost`, port `3306`,
utilisateur `root`, pas de mot de passe) :
```bash
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=root
export DB_PASSWORD=votre_mot_de_passe
export DB_NAME=bi_fraude
```

### 2. Lancer le pipeline
```bash
cd python
pip install -r requirements.txt

python 01_clean_data.py                  # nettoyage -> data/clean/*.csv + tables MySQL
python 02_fraud_rules.py                 # ajoute le scoring de fraude
python 03_build_views_and_calendar.py    # vues SQL + calendrier + exports CSV
```

À la fin, tout est dans la base MySQL `bi_fraude` : les tables sources
nettoyées, la table `transactions_flagged`, la table `dim_date` et les
6 vues `vw_*` prêtes pour l'analyse et Power BI. Les mêmes données sont
aussi exportées en CSV dans `data/clean/` (pratique pour vérifier à l'œil
ou pour importer dans Power BI sans configurer de pilote MySQL).

---

## 1. Nettoyage des données (Python / pandas)

`01_clean_data.py` traite chacune des anomalies volontairement introduites
dans le dataset :

| Anomalie                          | Traitement appliqué |
|-----------------------------------|----------------------|
| Valeurs manquantes (noms, dates, adresses) | Texte → `"Inconnu"` ; dates → `NaT` (conservées comme manquantes, pas devinées) |
| Doublons exacts / doublons de clé primaire | Supprimés (`drop_duplicates`), comptés dans le rapport qualité |
| Formats de date incohérents        | Parsing robuste avec `pandas.to_datetime(..., format="mixed")` |
| Dates futures impossibles          | Invalidées (mises à `NaT`) ou flaguées (`is_future_date` pour les transactions) |
| Montants/nombres en texte (virgules, espaces) | Reconversion en `float` |
| Espaces multiples / casse incohérente | `strip()`, normalisation des espaces, `title case` |
| IDs non séquentiels                | Conservés tels quels (ce sont des clés, pas des anomalies à corriger) — intégrité référentielle vérifiée et flaguée (`is_orphan_*`) |

Le détail chiffré de chaque correction est écrit dans
`docs/data_quality_report.csv`.

---

## 2. Détection de fraude par règles métier

`02_fraud_rules.py` calcule un **score de risque (0-100)** par transaction à
partir de 6 règles pondérées :

| Règle | Description | Poids |
|-------|--------------|-------|
| R1 | Montant > moyenne + 3σ du compte émetteur | 25 |
| R2 | Transaction nocturne (22h-6h) + montant élevé (> P90) | 15 |
| R3 | Auto-transfert (compte origine = compte destination) | 15 |
| R4 | Rafale : plus de 5 transactions du même compte en 60 min | 20 |
| R5 | Montant ≥ 90% du solde du compte (vidage de compte) | 20 |
| R6 | Compte émetteur inactif/fermé | 25 |

Une transaction avec un score **≥ 50** est marquée `is_suspected_fraud = 1`.
Les poids sont volontairement simples et modifiables dans le script.

---

## 3. Requêtes SQL (`sql/02_kpi_queries.sql`)

11 blocs de requêtes couvrant les KPI bancaires standards : balance totale,
répartition par type/statut de compte, NPL ratio des prêts, tendance
mensuelle des transactions, top clients, performance par agence,
indicateurs de fraude, segmentation client, acquisition de comptes.

Testez-les directement :
```bash
mysql -u root -p bi_fraude < sql/02_kpi_queries.sql
```

---

## 4. Dashboard Power BI

Voir `powerbi/README_PowerBI.md` pour le guide complet (import des données,
modèle en étoile, relations, pages suggérées) et `powerbi/dax_measures.txt`
pour les mesures DAX prêtes à l'emploi.

Résumé rapide :
1. Importer les fichiers `vw_*.csv` et `dim_date.csv` depuis `data/clean/`.
2. Créer les relations (voir schéma en étoile dans le guide).
3. Copier les mesures DAX.
4. Construire 5 pages : Vue d'ensemble, Comptes & Prêts, Transactions,
   Fraude & Risque, Clients.

---

## Limites connues

- Le score de fraude est **heuristique** (règles), pas un modèle entraîné —
  à valider/ajuster avec un expert métier avant tout usage réel.
- Les données sont **100% synthétiques** (aucune donnée personnelle réelle).
- `dim_date` couvre toute la plage 2020-2026 y compris les dates futures
  aberrantes détectées dans le dataset ; filtrez-les si besoin dans Power BI.
