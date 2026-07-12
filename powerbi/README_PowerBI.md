# Dashboard Power BI — KPI Bancaires & Fraude

Ce dossier documente comment construire le dashboard Power BI a partir des
donnees nettoyees produites par le pipeline Python + SQL (dossier `../data/clean/`
et `../sql/`). Power BI Desktop n'est pas disponible dans cet environnement
d'execution : ce guide vous donne toutes les etapes et le code DAX pretes
a copier-coller une fois le fichier ouvert sur votre machine.

---

## 1. Importer les donnees

Deux options, au choix :

### Option A — Import CSV (le plus simple, aucun pilote a installer)
Dans Power BI Desktop : **Accueil > Obtenir les donnees > Texte/CSV**,
puis importer chaque fichier de `data/clean/` :

- `vw_fact_transactions.csv` → table de faits principale
- `vw_dim_customer_360.csv` → dimension client
- `vw_dim_account.csv` → dimension compte
- `vw_fact_loans.csv` → table de faits prets
- `dim_date.csv` → calendrier
- `vw_kpi_monthly_summary.csv` et `vw_fraud_summary.csv` (optionnel,
  utiles pour verifier vos mesures DAX ou comme raccourci si vous ne
  voulez pas les recalculer en DAX)

### Option B — Connexion directe à la base MySQL (`bi_fraude`)
**Obtenir les données > Base de données MySQL** (connecteur natif Power BI,
aucun pilote à installer séparément) : renseignez le serveur
(`hôte:port`), la base `bi_fraude`, puis sélectionnez directement les
vues `vw_*` (déjà prêtes, pas besoin de refaire les jointures dans
Power Query).

> Recommandation : commencez par l'Option A pour aller vite, migrez vers
> l'Option B si vous voulez rafraichir automatiquement le dashboard a
> chaque nouvelle execution du pipeline Python.

---

## 2. Modele de donnees (schema en etoile)

```
                 dim_date
                     |
   dim_customer_360 -+- fact_transactions -+- dim_account
                     |                      |
                 fact_loans -----------------+
```

Relations a creer dans **Modelisation > Gerer les relations** :

| Table 1                  | Colonne              | Table 2            | Colonne     | Cardinalite     |
|---------------------------|-----------------------|----------------------|--------------|-----------------|
| vw_fact_transactions       | AccountOriginID        | vw_dim_account       | AccountID    | Plusieurs-vers-1 |
| vw_fact_transactions       | AnneeMois              | dim_date (colonne AnneeMois) | AnneeMois | Plusieurs-vers-1 |
| vw_dim_account             | CustomerID              | vw_dim_customer_360 | CustomerID   | Plusieurs-vers-1 |
| vw_fact_loans              | AccountID               | vw_dim_account       | AccountID    | Plusieurs-vers-1 |

Astuce : marquez `dim_date` comme **table de dates officielle** (clic droit
sur la table > "Marquer comme table de dates") pour activer le "time
intelligence" DAX (`TOTALYTD`, `SAMEPERIODLASTYEAR`, etc.).

---

## 3. Pages suggerees pour le dashboard

1. **Vue d'ensemble** — cartes KPI (balance totale, nb clients, nb comptes,
   volume de transactions), courbe d'evolution mensuelle du volume/montant.
2. **Portefeuille comptes & prets** — repartition par type de compte/statut,
   encours de prets par statut, NPL ratio.
3. **Transactions** — repartition par type, par agence, par heure/jour
   (heatmap), tendance mensuelle.
4. **Fraude & risque** — taux de transactions suspectes, score de risque
   moyen par agence, top transactions a risque (table triee), repartition
   par regle declenchee (R1 a R6).
5. **Clients** — segmentation par type de client, top clients par balance,
   carte geographique par ville/pays (colonnes `Ville`/`Pays` de
   `vw_dim_customer_360`).

---

## 4. Mesures DAX a creer

Voir le fichier [`dax_measures.txt`](./dax_measures.txt) pour le code complet,
pret a copier dans **Modelisation > Nouvelle mesure**.

Resume des mesures principales :

- `Balance Totale`
- `Nb Clients`, `Nb Comptes`, `Nb Transactions`
- `Montant Total Transactions`, `Montant Moyen Transaction`
- `Taux de Fraude %`
- `Montant Suspect Total`
- `Encours Prets`, `NPL Ratio %`
- `Evolution Montant MoM %` (variation mois sur mois)

---

## 5. Mise en forme

- Utilisez un theme sombre ou "Executive" (Affichage > Themes) adapte a un
  contexte bancaire/reporting.
- Formatez les montants en devise avec 2 decimales.
- Ajoutez un slicer sur `dim_date` (plage de dates), sur `Agence` et sur
  `TypeTransaction` pour permettre le filtrage interactif.
- Sur la page Fraude, utilisez une jauge (gauge) pour `Taux de Fraude %`
  avec seuils colores (vert < 0.5%, orange 0.5-2%, rouge > 2%).
