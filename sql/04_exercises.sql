-- =========================================================
-- 4. EXERCISES: test copy, time travel, automatic checks, read-only access
-- Everything destructive happens on a COPY. The raw table is never touched.
-- Run one statement at a time with Ctrl+Enter.
-- =========================================================

USE WAREHOUSE PREP_WH;
USE SCHEMA BATCH_MONITOR.RAW;


-- 4a. Zero-copy clone: an instant test copy of the raw table.
--     Nothing is physically copied, so it's instant and costs nothing
--     until you change something in the copy.
CREATE OR REPLACE TABLE LAB_RESULTS_DEV CLONE LAB_RESULTS_RAW;

SELECT COUNT(*) AS dev_rows FROM LAB_RESULTS_DEV;      -- expect 1005


-- 4b. Simulate a mistake on the copy: delete all 34 batches of product code 25
DELETE FROM LAB_RESULTS_DEV WHERE CODE = '25';

-- Run this RIGHT after the delete. It remembers which statement did the delete.
SET delete_qid = LAST_QUERY_ID();

SELECT (SELECT COUNT(*) FROM LAB_RESULTS_DEV) AS dev_rows,   -- expect 971
       (SELECT COUNT(*) FROM LAB_RESULTS_RAW) AS raw_rows;   -- expect 1005 (original untouched)


-- 4c. Time Travel: look at the copy as it was just before the delete
SELECT COUNT(*) AS rows_before_delete
FROM LAB_RESULTS_DEV BEFORE (STATEMENT => $delete_qid);   -- expect 1005

-- Recover: pull the deleted batches back out of that past version
INSERT INTO LAB_RESULTS_DEV
SELECT * FROM LAB_RESULTS_DEV BEFORE (STATEMENT => $delete_qid)
WHERE CODE = '25';

SELECT COUNT(*) AS dev_rows FROM LAB_RESULTS_DEV;      -- expect 1005 again


-- 4d. UNDROP: delete the whole table, then bring it back
DROP TABLE LAB_RESULTS_DEV;

SHOW TABLES LIKE 'LAB_RESULTS_DEV';                    -- expect no rows: it's gone

UNDROP TABLE LAB_RESULTS_DEV;

SELECT COUNT(*) AS dev_rows FROM LAB_RESULTS_DEV;      -- expect 1005: it's back


-- 4e. Automatic duplicate check (a Data Metric Function)

-- First, run the check by hand on the raw table
SELECT SNOWFLAKE.CORE.DUPLICATE_COUNT(
         SELECT BATCH FROM LAB_RESULTS_RAW) AS duplicate_batches;   -- expect 0

-- Make it automatic on the copy: the check runs whenever the data changes
ALTER TABLE LAB_RESULTS_DEV SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';
ALTER TABLE LAB_RESULTS_DEV ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (BATCH);

-- Simulate an accidental double load: add batch 500 a second time
INSERT INTO LAB_RESULTS_DEV SELECT * FROM LAB_RESULTS_DEV WHERE BATCH = '500';

-- Instant proof by hand that the duplicate is there
SELECT SNOWFLAKE.CORE.DUPLICATE_COUNT(
         SELECT BATCH FROM LAB_RESULTS_DEV) AS duplicate_batches;   -- expect above 0

-- Wait about 5 minutes, then see what the AUTOMATIC check recorded on its own.
-- Expect a DUPLICATE_COUNT row for LAB_RESULTS_DEV with a value above 0.
-- Nothing yet? Wait a few more minutes and run it again.
SELECT *
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS
WHERE TABLE_NAME = 'LAB_RESULTS_DEV'
ORDER BY MEASUREMENT_TIME DESC;


-- 4f. Read-only role: can read the clean view and nothing else
CREATE ROLE IF NOT EXISTS BATCH_READER;
GRANT USAGE ON WAREHOUSE PREP_WH TO ROLE BATCH_READER;                   -- may use the engine
GRANT USAGE ON DATABASE BATCH_MONITOR TO ROLE BATCH_READER;              -- may enter the database
GRANT USAGE ON SCHEMA BATCH_MONITOR.CLEAN TO ROLE BATCH_READER;          -- may enter CLEAN only
GRANT SELECT ON VIEW BATCH_MONITOR.CLEAN.LAB_RESULTS TO ROLE BATCH_READER;  -- may read the view

-- Give the role to yourself so you can test it
SET my_user = (SELECT '"' || CURRENT_USER() || '"');
GRANT ROLE BATCH_READER TO USER IDENTIFIER($my_user);

-- Switch into it and test
USE ROLE BATCH_READER;
USE WAREHOUSE PREP_WH;

SELECT COUNT(*) FROM BATCH_MONITOR.CLEAN.LAB_RESULTS;     -- works: expect 1005
SELECT COUNT(*) FROM BATCH_MONITOR.RAW.LAB_RESULTS_RAW;   -- fails: "does not exist or not authorized"
CREATE TABLE BATCH_MONITOR.CLEAN.TEST_WRITE (X INT);      -- fails: "insufficient privileges"

-- Switch back to your normal role. Do not skip this.
USE ROLE ACCOUNTADMIN;   -- or whichever role your step 1 check showed
