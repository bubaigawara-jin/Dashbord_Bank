-- =====================================================================
-- 02_kpi_queries.sql
-- Requetes des KPI bancaires standards, a executer sur la base MySQL 'bi_fraude'
-- (syntaxe MySQL 8+ ; adaptations mineures pour PostgreSQL signalees en
-- mineures signalees en commentaire : STRFTIME -> TO_CHAR/DATE_TRUNC).
--
-- Ces requetes alimentent directement les visuels du dashboard Power BI
-- (voir /powerbi/README_PowerBI.md) ou peuvent etre executees telles
-- quelles pour de l'analyse ad hoc.
-- =====================================================================


-- ---------------------------------------------------------------
-- KPI 1 : Vue d'ensemble du portefeuille (balance totale, nb comptes/clients)
-- ---------------------------------------------------------------
SELECT
    COUNT(DISTINCT c.CustomerID)                AS nb_clients,
    COUNT(DISTINCT a.AccountID)                 AS nb_comptes,
    ROUND(SUM(a.Balance), 2)                    AS balance_totale,
    ROUND(AVG(a.Balance), 2)                    AS balance_moyenne_compte
FROM customers c
JOIN accounts a ON a.CustomerID = c.CustomerID;


-- ---------------------------------------------------------------
-- KPI 2 : Balance totale et nombre de comptes par type de compte et statut
-- ---------------------------------------------------------------
SELECT
    at.TypeName          AS type_compte,
    ast.StatusName        AS statut_compte,
    COUNT(*)              AS nb_comptes,
    ROUND(SUM(a.Balance), 2) AS balance_totale,
    ROUND(AVG(a.Balance), 2) AS balance_moyenne
FROM accounts a
JOIN account_types at   ON at.AccountTypeID = a.AccountTypeID
JOIN account_statuses ast ON ast.AccountStatusID = a.AccountStatusID
GROUP BY at.TypeName, ast.StatusName
ORDER BY balance_totale DESC;


-- ---------------------------------------------------------------
-- KPI 3 : Taux de comptes actifs vs inactifs (%)
-- ---------------------------------------------------------------
SELECT
    ast.StatusName AS statut_compte,
    COUNT(*)       AS nb_comptes,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM accounts), 2) AS pct_du_total
FROM accounts a
JOIN account_statuses ast ON ast.AccountStatusID = a.AccountStatusID
GROUP BY ast.StatusName
ORDER BY nb_comptes DESC;


-- ---------------------------------------------------------------
-- KPI 4 : Portefeuille de prets - encours, taux moyen, NPL ratio
--   (NPL = Non Performing Loan, ici approxime par le statut "Default")
-- ---------------------------------------------------------------
SELECT
    ls.StatusName                                AS statut_pret,
    COUNT(*)                                     AS nb_prets,
    ROUND(SUM(l.PrincipalAmount), 2)             AS encours_total,
    ROUND(AVG(l.InterestRate) * 100, 2)          AS taux_interet_moyen_pct,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM loans), 2) AS pct_du_portefeuille
FROM loans l
JOIN loan_statuses ls ON ls.LoanStatusID = l.LoanStatusID
GROUP BY ls.StatusName
ORDER BY encours_total DESC;

-- NPL ratio global (statuts consideres "non performants" : Overdue/Default/Delinquent
-- selon le libelle present dans loan_statuses - a adapter si le dictionnaire change)
SELECT
    ROUND(
        100.0 * SUM(CASE WHEN ls.StatusName LIKE '%Overdue%' OR ls.StatusName LIKE '%Default%'
                          THEN l.PrincipalAmount ELSE 0 END)
        / SUM(l.PrincipalAmount)
    , 2) AS npl_ratio_pct
FROM loans l
JOIN loan_statuses ls ON ls.LoanStatusID = l.LoanStatusID;


-- ---------------------------------------------------------------
-- KPI 5 : Volume et montant des transactions par mois (tendance)
--   MySQL : DATE_FORMAT(date, '%Y-%m')  |  PostgreSQL : to_char(date, 'YYYY-MM')
-- ---------------------------------------------------------------
SELECT
    DATE_FORMAT(TransactionDate, '%Y-%m') AS mois,
    COUNT(*)                           AS nb_transactions,
    ROUND(SUM(Amount), 2)              AS montant_total,
    ROUND(AVG(Amount), 2)              AS montant_moyen
FROM transactions
WHERE TransactionDate IS NOT NULL
GROUP BY mois
ORDER BY mois;


-- ---------------------------------------------------------------
-- KPI 6 : Repartition des transactions par type
-- ---------------------------------------------------------------
SELECT
    tt.TypeName             AS type_transaction,
    COUNT(*)                AS nb_transactions,
    ROUND(SUM(t.Amount), 2) AS montant_total,
    ROUND(AVG(t.Amount), 2) AS montant_moyen
FROM transactions t
JOIN transaction_types tt ON tt.TransactionTypeID = t.TransactionTypeID
GROUP BY tt.TypeName
ORDER BY montant_total DESC;


-- ---------------------------------------------------------------
-- KPI 7 : Top 10 clients par balance totale (tous comptes confondus)
-- ---------------------------------------------------------------
SELECT
    c.CustomerID,
    CONCAT(c.FirstName, ' ', c.LastName) AS client,
    COUNT(a.AccountID)               AS nb_comptes,
    ROUND(SUM(a.Balance), 2)         AS balance_totale
FROM customers c
JOIN accounts a ON a.CustomerID = c.CustomerID
GROUP BY c.CustomerID, client
ORDER BY balance_totale DESC
LIMIT 10;


-- ---------------------------------------------------------------
-- KPI 8 : Performance par agence (branch) - volume et montant
-- ---------------------------------------------------------------
SELECT
    b.BranchName,
    COUNT(t.TransactionID)   AS nb_transactions,
    ROUND(SUM(t.Amount), 2)  AS montant_total,
    ROUND(AVG(t.Amount), 2)  AS montant_moyen
FROM transactions t
JOIN branches b ON b.BranchID = t.BranchID
GROUP BY b.BranchName
ORDER BY montant_total DESC;


-- ---------------------------------------------------------------
-- KPI 9 : Indicateurs de fraude (necessite transactions_flagged,
--          generee par 02_fraud_rules.py)
-- ---------------------------------------------------------------

-- 9.1 Taux global de transactions suspectes
SELECT
    COUNT(*)                                             AS total_transactions,
    SUM(is_suspected_fraud)                               AS nb_suspectes,
    ROUND(100.0 * SUM(is_suspected_fraud) / COUNT(*), 3)  AS taux_fraude_pct,
    ROUND(SUM(CASE WHEN is_suspected_fraud = 1 THEN Amount ELSE 0 END), 2) AS montant_suspect_total
FROM transactions_flagged;

-- 9.2 Repartition des transactions suspectes par regle declenchee
SELECT 'R1_amount_outlier'   AS regle, SUM(rule_R1_amount_outlier)   AS occurrences FROM transactions_flagged
UNION ALL
SELECT 'R2_night_high_amount', SUM(rule_R2_night_high_amount)        FROM transactions_flagged
UNION ALL
SELECT 'R3_self_transfer',     SUM(rule_R3_self_transfer)            FROM transactions_flagged
UNION ALL
SELECT 'R4_burst',             SUM(rule_R4_burst)                    FROM transactions_flagged
UNION ALL
SELECT 'R5_drains_balance',    SUM(rule_R5_drains_balance)           FROM transactions_flagged
UNION ALL
SELECT 'R6_inactive_account',  SUM(rule_R6_inactive_account)         FROM transactions_flagged
ORDER BY occurrences DESC;

-- 9.3 Top 10 des transactions les plus a risque
SELECT
    TransactionID, AccountOriginID, AccountDestinationID,
    Amount, TransactionDate, fraud_risk_score
FROM transactions_flagged
ORDER BY fraud_risk_score DESC, Amount DESC
LIMIT 10;

-- 9.4 Score de risque moyen par agence
SELECT
    b.BranchName,
    ROUND(AVG(tf.fraud_risk_score), 2) AS score_risque_moyen,
    SUM(tf.is_suspected_fraud)         AS nb_suspectes
FROM transactions_flagged tf
JOIN branches b ON b.BranchID = tf.BranchID
GROUP BY b.BranchName
ORDER BY score_risque_moyen DESC;


-- ---------------------------------------------------------------
-- KPI 10 : Segmentation clients (particulier vs entreprise)
-- ---------------------------------------------------------------
SELECT
    ct.TypeName                     AS type_client,
    COUNT(DISTINCT c.CustomerID)    AS nb_clients,
    ROUND(SUM(a.Balance), 2)        AS balance_totale,
    ROUND(AVG(a.Balance), 2)        AS balance_moyenne
FROM customers c
JOIN customer_types ct ON ct.CustomerTypeID = c.CustomerTypeID
JOIN accounts a         ON a.CustomerID = c.CustomerID
GROUP BY ct.TypeName
ORDER BY balance_totale DESC;


-- ---------------------------------------------------------------
-- KPI 11 : Nouveaux comptes ouverts par mois (acquisition)
-- ---------------------------------------------------------------
SELECT
    DATE_FORMAT(OpeningDate, '%Y-%m') AS mois_ouverture,
    COUNT(*)                       AS nb_nouveaux_comptes
FROM accounts
WHERE OpeningDate IS NOT NULL
GROUP BY mois_ouverture
ORDER BY mois_ouverture;
