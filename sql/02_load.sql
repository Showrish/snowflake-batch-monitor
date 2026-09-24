-- =========================================================
-- 2. LOAD Laboratory.csv
-- Run each block top to bottom with Ctrl+Enter.
-- One pause in the middle to upload the file through the UI.
-- =========================================================

USE WAREHOUSE PREP_WH;
USE SCHEMA BATCH_MONITOR.RAW;


-- 2a. Describe the file so Snowflake reads it correctly
CREATE FILE FORMAT IF NOT EXISTS LAB_CSV
  TYPE = CSV
  FIELD_DELIMITER = ';'        -- columns are separated by semicolons, not commas
  RECORD_DELIMITER = '\r\n'    -- each row ends with a Windows line break
  SKIP_HEADER = 1;             -- the first line is column names, not data


-- 2b. A landing spot for the file inside Snowflake (called a "stage")
CREATE STAGE IF NOT EXISTS LAB_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')   -- standard server-side encryption
  DIRECTORY = (ENABLE = TRUE);            -- lets you see the file in the UI


-- 2c. The raw table. Every column is text, so the file lands exactly as received.
--     All cleaning happens later in a view, so this table is never edited.
--     START is renamed START_MONTH because START is a reserved word in Snowflake.
--     Column order matches the file exactly, because COPY INTO loads by position.
CREATE TABLE IF NOT EXISTS LAB_RESULTS_RAW (
  -- identifiers and batch info
  BATCH VARCHAR, CODE VARCHAR, STRENGTH VARCHAR, SIZE VARCHAR,
  START_MONTH VARCHAR,
  -- genealogy: which raw material lots went into the batch
  API_CODE VARCHAR, API_BATCH VARCHAR, SMCC_BATCH VARCHAR, LACTOSE_BATCH VARCHAR,
  STARCH_BATCH VARCHAR,
  -- incoming raw material tests
  API_WATER VARCHAR, API_TOTAL_IMPURITIES VARCHAR, API_L_IMPURITY VARCHAR, API_CONTENT VARCHAR,
  API_PS01 VARCHAR, API_PS05 VARCHAR, API_PS09 VARCHAR, LACTOSE_WATER VARCHAR,
  LACTOSE_SIEVE0045 VARCHAR, LACTOSE_SIEVE015 VARCHAR, LACTOSE_SIEVE025 VARCHAR, SMCC_WATER VARCHAR,
  SMCC_TD VARCHAR, SMCC_BD VARCHAR, SMCC_PS01 VARCHAR, SMCC_PS05 VARCHAR,
  SMCC_PS09 VARCHAR, STARCH_PH VARCHAR, STARCH_WATER VARCHAR,
  -- in-process tablet checks
  TBL_MIN_THICKNESS VARCHAR, TBL_MAX_THICKNESS VARCHAR, FCT_MIN_THICKNESS VARCHAR, FCT_MAX_THICKNESS VARCHAR,
  TBL_MIN_WEIGHT VARCHAR, TBL_MAX_WEIGHT VARCHAR, TBL_RSD_WEIGHT VARCHAR, FCT_RSD_WEIGHT VARCHAR,
  TBL_MIN_HARDNESS VARCHAR, TBL_MAX_HARDNESS VARCHAR, TBL_AV_HARDNESS VARCHAR, FCT_MIN_HARDNESS VARCHAR,
  FCT_MAX_HARDNESS VARCHAR, FCT_AV_HARDNESS VARCHAR, TBL_MAX_DIAMETER VARCHAR, FCT_MAX_DIAMETER VARCHAR,
  TBL_TENSILE VARCHAR, FCT_TENSILE VARCHAR, TBL_YIELD VARCHAR, BATCH_YIELD VARCHAR,
  -- final product quality (RESODUAL is the source file's own spelling)
  DISSOLUTION_AV VARCHAR, DISSOLUTION_MIN VARCHAR, RESODUAL_SOLVENT VARCHAR, IMPURITIES_TOTAL VARCHAR,
  IMPURITY_O VARCHAR, IMPURITY_L VARCHAR
);


-- >>> PAUSE: upload the file now (UI, not SQL) <<<
-- Left nav: Data » Databases (newer layouts may call it Catalog)
--   » BATCH_MONITOR » RAW » Stages » LAB_STAGE
-- Click + Files (top right), drop in Laboratory.csv, click Upload.


-- 2d. Confirm the file is in the stage. Expect one row.
LIST @LAB_STAGE;


-- 2e. Dry run: checks the whole file for errors WITHOUT loading anything.
--     Expect an empty result, which means zero errors.
COPY INTO LAB_RESULTS_RAW
  FROM @LAB_STAGE
  FILE_FORMAT = (FORMAT_NAME = 'LAB_CSV')
  VALIDATION_MODE = 'RETURN_ERRORS';


-- 2f. The real load. All or nothing: if any row fails, nothing loads.
--     Expect status LOADED, rows_parsed 1005, rows_loaded 1005, errors_seen 0.
--     If you run it twice, Snowflake skips the file because it remembers
--     loading it. That is a built-in guard against duplicate loads.
COPY INTO LAB_RESULTS_RAW
  FROM @LAB_STAGE
  FILE_FORMAT = (FORMAT_NAME = 'LAB_CSV')
  ON_ERROR = 'ABORT_STATEMENT';


-- 2g. Check the load against what was found in the file
SELECT COUNT(*)                    AS total_rows,      -- expect 1005
       COUNT(DISTINCT BATCH)       AS unique_batches,  -- expect 1005 (no duplicates)
       COUNT(DISTINCT CODE)        AS product_codes,   -- expect 25
       COUNT(DISTINCT START_MONTH) AS months           -- expect 29
FROM LAB_RESULTS_RAW;

-- Stray line-break characters stuck on the last column? Expect 0.
SELECT COUNT(*) AS stray_line_breaks
FROM LAB_RESULTS_RAW
WHERE CONTAINS(IMPURITY_L, '\r');
