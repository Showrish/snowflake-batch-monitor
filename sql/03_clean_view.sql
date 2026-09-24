-- =========================================================
-- 3. CLEAN VIEW on top of the raw table
-- Before running: 2g should have shown 1005 / 1005 / 25 / 29,
-- and 0 stray line breaks. If not, stop and send a screenshot.
-- =========================================================

USE WAREHOUSE PREP_WH;


-- 3a. A separate schema for cleaned data, so raw and clean never mix
CREATE SCHEMA IF NOT EXISTS BATCH_MONITOR.CLEAN;


-- 3b. The clean view. It reads the raw table and fixes everything on the way out.
--     The raw table itself is never changed.
CREATE OR REPLACE VIEW BATCH_MONITOR.CLEAN.LAB_RESULTS AS
SELECT
  -- identifiers stay as text: they are labels, you never do math on them
  r.BATCH,
  TO_NUMBER(r.BATCH) AS BATCH_SEQ,   -- numeric copy for sorting only (production order within a product code)
  r.CODE AS PRODUCT_CODE,

  -- fix the truncated strength labels
  CASE r.STRENGTH
    WHEN '5MG' THEN '5 mg'
    WHEN '10M' THEN '10 mg'
    WHEN '20M' THEN '20 mg'
    WHEN '40M' THEN '40 mg'
  END AS STRENGTH,                   -- anything unexpected becomes NULL, and check 3d catches it

  TO_NUMBER(r.SIZE) AS BATCH_SIZE,

  -- turn Slovenian month labels like 'maj.19' into a real date (first of the month)
  DATE_FROM_PARTS(
    2000 + TO_NUMBER(SPLIT_PART(r.START_MONTH, '.', 2)),    -- '19'  becomes 2019
    CASE SPLIT_PART(r.START_MONTH, '.', 1)                   -- 'maj' becomes 5
      WHEN 'jan' THEN 1  WHEN 'feb' THEN 2  WHEN 'mar' THEN 3
      WHEN 'apr' THEN 4  WHEN 'maj' THEN 5  WHEN 'jun' THEN 6
      WHEN 'jul' THEN 7  WHEN 'avg' THEN 8  WHEN 'sep' THEN 9
      WHEN 'okt' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
    END,
    1
  ) AS START_MONTH,

  -- genealogy lot IDs, kept as text
  r.API_CODE, r.API_BATCH, r.SMCC_BATCH, r.LACTOSE_BATCH, r.STARCH_BATCH,

  -- Every measurement: strip spaces, treat blank as missing (NULL), convert to a number.
  -- TO_DOUBLE is strict on purpose. Blanks become NULL, but any other bad value
  -- makes the query fail loudly instead of quietly disappearing.
  -- incoming raw material tests
  TO_DOUBLE(NULLIF(TRIM(r.API_WATER), '')) AS API_WATER,
  TO_DOUBLE(NULLIF(TRIM(r.API_TOTAL_IMPURITIES), '')) AS API_TOTAL_IMPURITIES,
  TO_DOUBLE(NULLIF(TRIM(r.API_L_IMPURITY), '')) AS API_L_IMPURITY,
  TO_DOUBLE(NULLIF(TRIM(r.API_CONTENT), '')) AS API_CONTENT,
  TO_DOUBLE(NULLIF(TRIM(r.API_PS01), '')) AS API_PS01,
  TO_DOUBLE(NULLIF(TRIM(r.API_PS05), '')) AS API_PS05,
  TO_DOUBLE(NULLIF(TRIM(r.API_PS09), '')) AS API_PS09,
  TO_DOUBLE(NULLIF(TRIM(r.LACTOSE_WATER), '')) AS LACTOSE_WATER,
  TO_DOUBLE(NULLIF(TRIM(r.LACTOSE_SIEVE0045), '')) AS LACTOSE_SIEVE0045,
  TO_DOUBLE(NULLIF(TRIM(r.LACTOSE_SIEVE015), '')) AS LACTOSE_SIEVE015,
  TO_DOUBLE(NULLIF(TRIM(r.LACTOSE_SIEVE025), '')) AS LACTOSE_SIEVE025,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_WATER), '')) AS SMCC_WATER,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_TD), '')) AS SMCC_TD,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_BD), '')) AS SMCC_BD,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_PS01), '')) AS SMCC_PS01,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_PS05), '')) AS SMCC_PS05,
  TO_DOUBLE(NULLIF(TRIM(r.SMCC_PS09), '')) AS SMCC_PS09,
  TO_DOUBLE(NULLIF(TRIM(r.STARCH_PH), '')) AS STARCH_PH,
  TO_DOUBLE(NULLIF(TRIM(r.STARCH_WATER), '')) AS STARCH_WATER,
  -- in-process tablet checks
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MIN_THICKNESS), '')) AS TBL_MIN_THICKNESS,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MAX_THICKNESS), '')) AS TBL_MAX_THICKNESS,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_MIN_THICKNESS), '')) AS FCT_MIN_THICKNESS,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_MAX_THICKNESS), '')) AS FCT_MAX_THICKNESS,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MIN_WEIGHT), '')) AS TBL_MIN_WEIGHT,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MAX_WEIGHT), '')) AS TBL_MAX_WEIGHT,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_RSD_WEIGHT), '')) AS TBL_RSD_WEIGHT,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_RSD_WEIGHT), '')) AS FCT_RSD_WEIGHT,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MIN_HARDNESS), '')) AS TBL_MIN_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MAX_HARDNESS), '')) AS TBL_MAX_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_AV_HARDNESS), '')) AS TBL_AV_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_MIN_HARDNESS), '')) AS FCT_MIN_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_MAX_HARDNESS), '')) AS FCT_MAX_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_AV_HARDNESS), '')) AS FCT_AV_HARDNESS,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_MAX_DIAMETER), '')) AS TBL_MAX_DIAMETER,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_MAX_DIAMETER), '')) AS FCT_MAX_DIAMETER,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_TENSILE), '')) AS TBL_TENSILE,
  TO_DOUBLE(NULLIF(TRIM(r.FCT_TENSILE), '')) AS FCT_TENSILE,
  TO_DOUBLE(NULLIF(TRIM(r.TBL_YIELD), '')) AS TBL_YIELD,
  TO_DOUBLE(NULLIF(TRIM(r.BATCH_YIELD), '')) AS BATCH_YIELD,
  -- final product quality
  TO_DOUBLE(NULLIF(TRIM(r.DISSOLUTION_AV), '')) AS DISSOLUTION_AV,
  TO_DOUBLE(NULLIF(TRIM(r.DISSOLUTION_MIN), '')) AS DISSOLUTION_MIN,
  TO_DOUBLE(NULLIF(TRIM(r.RESODUAL_SOLVENT), '')) AS RESIDUAL_SOLVENT,   -- source spells it RESODUAL, fixed here
  TO_DOUBLE(NULLIF(TRIM(r.IMPURITIES_TOTAL), '')) AS IMPURITIES_TOTAL,
  TO_DOUBLE(NULLIF(TRIM(r.IMPURITY_O), '')) AS IMPURITY_O,
  TO_DOUBLE(NULLIF(TRIM(r.IMPURITY_L), '')) AS IMPURITY_L
FROM BATCH_MONITOR.RAW.LAB_RESULTS_RAW r;


-- 3c. Same row count as raw, and every month parsed
SELECT COUNT(*)                      AS total_rows,        -- expect 1005
       COUNT_IF(START_MONTH IS NULL) AS unparsed_months,   -- expect 0
       MIN(START_MONTH)              AS first_month,       -- expect 2018-11-01
       MAX(START_MONTH)              AS last_month,        -- expect 2021-04-01
       COUNT(DISTINCT START_MONTH)   AS months             -- expect 29
FROM BATCH_MONITOR.CLEAN.LAB_RESULTS;


-- 3d. Every strength label mapped. Expect 4 rows and no NULL:
--     20 mg 445, 5 mg 249, 10 mg 213, 40 mg 98
SELECT STRENGTH, COUNT(*) AS batches
FROM BATCH_MONITOR.CLEAN.LAB_RESULTS
GROUP BY STRENGTH
ORDER BY batches DESC;


-- 3e. Where the missing values sit, by API source.
--     Expect every missing API result under API_CODE 3, and the 10 missing
--     tablet weights split 8 under code 3 and 2 under code 4.
--     The paper only mentions the API gaps. The tablet weights are the finding it missed.
SELECT API_CODE,
       COUNT(*)                               AS batches,             -- 150, 15, 481, 24, 335
       COUNT_IF(API_WATER IS NULL)            AS no_api_water,        -- code 3: 26
       COUNT_IF(API_TOTAL_IMPURITIES IS NULL) AS no_api_impurities,   -- code 3: 67
       COUNT_IF(API_L_IMPURITY IS NULL)       AS no_api_l_impurity,   -- code 3: 370
       COUNT_IF(TBL_MIN_WEIGHT IS NULL)       AS no_tablet_weight     -- code 3: 8, code 4: 2
FROM BATCH_MONITOR.CLEAN.LAB_RESULTS
GROUP BY API_CODE
ORDER BY API_CODE;


-- 3f. The numbers survived conversion. These match what Python computed
--     from the raw file, so Snowflake and Python agree.
SELECT ROUND(AVG(DISSOLUTION_AV), 3) AS avg_dissolution,   -- expect 90.65
       MIN(DISSOLUTION_AV)           AS min_dissolution,   -- expect 82.5
       MAX(DISSOLUTION_AV)           AS max_dissolution    -- expect 102.67
FROM BATCH_MONITOR.CLEAN.LAB_RESULTS;
