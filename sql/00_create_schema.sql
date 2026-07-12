-- =====================================================================
-- 00_create_schema.sql
-- Schema relationnel (type "star schema") pour l'analyse BI bancaire.
-- Syntaxe MySQL 8+ (adaptable a PostgreSQL/SQL Server en changeant les
-- types marques en commentaire).
--
-- A executer une fois, apres avoir cree la base :
--   CREATE DATABASE bi_fraude CHARACTER SET utf8mb4;
--   USE bi_fraude;
--   SOURCE 00_create_schema.sql;
--
-- Le pipeline Python (01_clean_data.py) cree deja ces tables
-- automatiquement dans MySQL via pandas.to_sql() (voir db_connection.py).
-- Ce fichier sert de reference si vous voulez un schema explicite avec
-- cles primaires/etrangeres et types stricts (recommande en production),
-- plutot que le schema auto-devine par pandas.
-- =====================================================================

-- ---------------------------------------------------------------
-- DIMENSIONS
-- ---------------------------------------------------------------

CREATE TABLE dim_customer_type (
    CustomerTypeID  INTEGER PRIMARY KEY,
    TypeName        VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_account_type (
    AccountTypeID   INTEGER PRIMARY KEY,
    TypeName        VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_account_status (
    AccountStatusID INTEGER PRIMARY KEY,
    StatusName      VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_loan_status (
    LoanStatusID    INTEGER PRIMARY KEY,
    StatusName      VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_transaction_type (
    TransactionTypeID INTEGER PRIMARY KEY,
    TypeName          VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_address (
    AddressID   INTEGER PRIMARY KEY,
    Street      VARCHAR(150),
    City        VARCHAR(100),
    Country     VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_branch (
    BranchID    INTEGER PRIMARY KEY,
    BranchName  VARCHAR(100) NOT NULL,
    AddressID   INTEGER REFERENCES dim_address(AddressID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE dim_customer (
    CustomerID      INTEGER PRIMARY KEY,
    FirstName       VARCHAR(100),
    LastName        VARCHAR(100),
    DateOfBirth     DATE,
    AddressID       INTEGER REFERENCES dim_address(AddressID),
    CustomerTypeID  INTEGER REFERENCES dim_customer_type(CustomerTypeID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table calendrier, generee a partir des dates min/max de transactions
-- (utile pour Power BI : relations sur les dates, time intelligence DAX)
CREATE TABLE dim_date (
    DateKey     DATE PRIMARY KEY,
    Year        INTEGER,
    Month       INTEGER,
    MonthName   VARCHAR(20),
    Day         INTEGER,
    DayOfWeek   INTEGER,
    DayName     VARCHAR(20),
    Quarter     INTEGER,
    IsWeekend   BOOLEAN
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------
-- FAITS / ENTITES OPERATIONNELLES
-- ---------------------------------------------------------------

CREATE TABLE fact_account (
    AccountID           INTEGER PRIMARY KEY,
    CustomerID          INTEGER REFERENCES dim_customer(CustomerID),
    AccountTypeID       INTEGER REFERENCES dim_account_type(AccountTypeID),
    AccountStatusID     INTEGER REFERENCES dim_account_status(AccountStatusID),
    Balance             NUMERIC(18,2),
    OpeningDate         DATE,
    is_orphan_customer  BOOLEAN
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_loan (
    LoanID              INTEGER PRIMARY KEY,
    AccountID           INTEGER REFERENCES fact_account(AccountID),
    LoanStatusID        INTEGER REFERENCES dim_loan_status(LoanStatusID),
    PrincipalAmount     NUMERIC(18,2),
    InterestRate        NUMERIC(9,6),
    StartDate           DATE,
    EstimatedEndDate    DATE,
    is_orphan_account   BOOLEAN
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fact_transaction (
    TransactionID           INTEGER PRIMARY KEY,
    AccountOriginID         INTEGER REFERENCES fact_account(AccountID),
    AccountDestinationID    INTEGER REFERENCES fact_account(AccountID),
    TransactionTypeID       INTEGER REFERENCES dim_transaction_type(TransactionTypeID),
    Amount                  NUMERIC(18,2),
    TransactionDate         DATETIME,
    BranchID                INTEGER REFERENCES dim_branch(BranchID),
    Description             VARCHAR(200),
    is_future_date          BOOLEAN,
    is_self_transfer        BOOLEAN,
    is_weekend              BOOLEAN,
    is_night                BOOLEAN,
    -- Colonnes ajoutees par 02_fraud_rules.py :
    fraud_risk_score        INTEGER,     -- 0 a 100
    is_suspected_fraud      SMALLINT     -- 0 / 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------
-- INDEX recommandes pour la performance des requetes BI
-- ---------------------------------------------------------------
CREATE INDEX idx_transaction_date       ON fact_transaction (TransactionDate);
CREATE INDEX idx_transaction_origin     ON fact_transaction (AccountOriginID);
CREATE INDEX idx_transaction_destination ON fact_transaction (AccountDestinationID);
CREATE INDEX idx_transaction_branch     ON fact_transaction (BranchID);
CREATE INDEX idx_account_customer       ON fact_account (CustomerID);
CREATE INDEX idx_loan_account           ON fact_loan (AccountID);
