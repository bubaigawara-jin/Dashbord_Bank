-- =====================================================================
-- 03_views.sql
-- Vues pretes a l'emploi pour brancher Power BI directement dessus
-- (connecteur Power BI natif "Base de donnees MySQL" > choisir ces vues
-- plutot que les tables brutes : elles font deja les jointures et
-- calculs les plus courants). Syntaxe MySQL 8+.
-- =====================================================================

-- ---------------------------------------------------------------
-- vw_fact_transactions : table de faits enrichie, prete pour Power BI
-- (grain = 1 ligne par transaction). C'est la table principale a
-- utiliser pour construire les visuels du dashboard.
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_fact_transactions;
CREATE VIEW vw_fact_transactions AS
SELECT
    tf.TransactionID,
    tf.TransactionDate,
    DATE_FORMAT(tf.TransactionDate, '%Y-%m') AS AnneeMois,
    tf.Amount,
    tt.TypeName            AS TypeTransaction,
    b.BranchName            AS Agence,
    tf.AccountOriginID,
    tf.AccountDestinationID,
    tf.is_weekend,
    tf.is_night,
    tf.is_self_transfer,
    tf.fraud_risk_score,
    tf.is_suspected_fraud
FROM transactions_flagged tf
JOIN transaction_types tt ON tt.TransactionTypeID = tf.TransactionTypeID
JOIN branches b            ON b.BranchID = tf.BranchID;


-- ---------------------------------------------------------------
-- vw_dim_customer_360 : vue client enrichie (type, adresse, nb comptes, balance)
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_dim_customer_360;
CREATE VIEW vw_dim_customer_360 AS
SELECT
    c.CustomerID,
    CONCAT(c.FirstName, ' ', c.LastName) AS NomComplet,
    c.DateOfBirth,
    ct.TypeName                       AS TypeClient,
    ad.City                           AS Ville,
    ad.Country                        AS Pays,
    COUNT(DISTINCT a.AccountID)       AS NbComptes,
    COALESCE(SUM(a.Balance), 0)       AS BalanceTotale
FROM customers c
LEFT JOIN customer_types ct ON ct.CustomerTypeID = c.CustomerTypeID
LEFT JOIN addresses ad      ON ad.AddressID = c.AddressID
LEFT JOIN accounts a        ON a.CustomerID = c.CustomerID
GROUP BY c.CustomerID, NomComplet, c.DateOfBirth, ct.TypeName, ad.City, ad.Country;


-- ---------------------------------------------------------------
-- vw_dim_account : comptes enrichis (type, statut, client)
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_dim_account;
CREATE VIEW vw_dim_account AS
SELECT
    a.AccountID,
    a.CustomerID,
    at.TypeName    AS TypeCompte,
    ast.StatusName AS StatutCompte,
    a.Balance,
    a.OpeningDate
FROM accounts a
JOIN account_types at    ON at.AccountTypeID = a.AccountTypeID
JOIN account_statuses ast ON ast.AccountStatusID = a.AccountStatusID;


-- ---------------------------------------------------------------
-- vw_fact_loans : prets enrichis (statut, compte, client)
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_fact_loans;
CREATE VIEW vw_fact_loans AS
SELECT
    l.LoanID,
    l.AccountID,
    a.CustomerID,
    ls.StatusName AS StatutPret,
    l.PrincipalAmount,
    l.InterestRate,
    l.StartDate,
    l.EstimatedEndDate
FROM loans l
JOIN loan_statuses ls ON ls.LoanStatusID = l.LoanStatusID
JOIN accounts a        ON a.AccountID = l.AccountID;


-- ---------------------------------------------------------------
-- vw_kpi_monthly_summary : synthese mensuelle prete pour le dashboard
-- (1 ligne par mois : volume, montant, taux de fraude)
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_kpi_monthly_summary;
CREATE VIEW vw_kpi_monthly_summary AS
SELECT
    DATE_FORMAT(TransactionDate, '%Y-%m') AS AnneeMois,
    COUNT(*)                            AS NbTransactions,
    ROUND(SUM(Amount), 2)               AS MontantTotal,
    ROUND(AVG(Amount), 2)               AS MontantMoyen,
    SUM(is_suspected_fraud)             AS NbSuspectes,
    ROUND(100.0 * SUM(is_suspected_fraud) / COUNT(*), 3) AS TauxFraudePct
FROM transactions_flagged
WHERE TransactionDate IS NOT NULL
GROUP BY AnneeMois
ORDER BY AnneeMois;


-- ---------------------------------------------------------------
-- vw_fraud_summary : synthese des regles de fraude declenchees
-- ---------------------------------------------------------------
DROP VIEW IF EXISTS vw_fraud_summary;
CREATE VIEW vw_fraud_summary AS
SELECT
    b.BranchName AS Agence,
    COUNT(*)                              AS NbTransactions,
    SUM(tf.is_suspected_fraud)            AS NbSuspectes,
    ROUND(AVG(tf.fraud_risk_score), 2)    AS ScoreRisqueMoyen,
    ROUND(SUM(CASE WHEN tf.is_suspected_fraud = 1 THEN tf.Amount ELSE 0 END), 2) AS MontantSuspectTotal
FROM transactions_flagged tf
JOIN branches b ON b.BranchID = tf.BranchID
GROUP BY b.BranchName;
