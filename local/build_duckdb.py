"""Build Batch Monitor's local DuckDB database from Laboratory.csv.

DuckDB port of the Snowflake pipeline in sql/01 to sql/03:

  BATCH_MONITOR.RAW.LAB_RESULTS_RAW   the CSV exactly as delivered, every column text
  BATCH_MONITOR.CLEAN.LAB_RESULTS     a view that types and fixes the data on read

The steps and expected values match the Snowflake build. The database is built
in a scratch folder and only replaces the existing one if every check passes,
so a failed build never leaves a half-built database behind.

Usage:
    python local/build_duckdb.py                       (looks for Laboratory.csv)
    python local/build_duckdb.py path/to/Laboratory.csv
"""
import csv
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
DB_NAME = "batch_monitor.duckdb"  # the file name becomes the catalog name BATCH_MONITOR
DB_PATH = REPO / DB_NAME
SCRATCH = REPO / ".build_tmp"

EXPECTED_COLUMNS = 55
EXPECTED_MEASUREMENTS = 45

# Raw header names that are labels, not measurements
LABELS = {"batch", "code", "strength", "size", "start",
          "api_code", "api_batch", "smcc_batch", "lactose_batch", "starch_batch"}

# Slovenian month abbreviations used in the start column
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
          "jul": 7, "avg": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12}

# Strength codes as stored (truncated) and their readable labels
STRENGTHS = {"5MG": "5 mg", "10M": "10 mg", "20M": "20 mg", "40M": "40 mg"}


def find_csv():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        candidates = [REPO / "Laboratory.csv", REPO / "data" / "Laboratory.csv"]
        path = next((p for p in candidates if p.exists()), candidates[0])
    if not path.exists():
        sys.exit(f"Can't find {path}. Download Laboratory.csv from figshare and put it "
                 "in the repo root, or pass its path.")
    return path.resolve()


def read_header(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return [name.strip() for name in next(csv.reader(f, delimiter=";"))]


def raw_name(header_name):
    """Same naming as the Snowflake raw table: upper case, with START renamed."""
    return "START_MONTH" if header_name.lower() == "start" else header_name.upper()


def raw_table_sql(header, reader):
    cols = ",\n    ".join(f'"{h}" AS "{raw_name(h)}"' for h in header)
    return f"CREATE TABLE raw.lab_results_raw AS\nSELECT\n    {cols}\nFROM {reader}"


def clean_view_sql(header):
    year_txt = "regexp_extract(TRIM(\"START_MONTH\"), '([0-9]+)', 1)"
    month_txt = "lower(regexp_extract(TRIM(\"START_MONTH\"), '([A-Za-z]+)', 1))"
    year_num = (f"CASE WHEN length({year_txt}) = 2 THEN 2000 + CAST({year_txt} AS INTEGER) "
                f"ELSE CAST({year_txt} AS INTEGER) END")
    month_num = (f"CASE {month_txt} "
                 + " ".join(f"WHEN '{k}' THEN {v}" for k, v in MONTHS.items()) + " END")
    strength = ("CASE TRIM(\"STRENGTH\") "
                + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in STRENGTHS.items()) + " END")

    cols = [
        '"BATCH"',
        'CAST(TRIM("BATCH") AS BIGINT) AS "BATCH_SEQ"',  # production order
        '"CODE" AS "PRODUCT_CODE"',
        f'{strength} AS "STRENGTH"',  # unmapped codes become NULL and fail a check
        'CAST(CAST(NULLIF(TRIM("SIZE"), \'\') AS DOUBLE) AS BIGINT) AS "BATCH_SIZE"',
        f'make_date({year_num}, {month_num}, 1) AS "START_MONTH"',  # first day of the month
        '"API_CODE"', '"API_BATCH"', '"SMCC_BATCH"', '"LACTOSE_BATCH"', '"STARCH_BATCH"',
    ]
    for h in header:
        if h.lower() in LABELS:
            continue
        out = "RESIDUAL_SOLVENT" if h.lower() == "resodual_solvent" else h.upper()
        # Strict cast, like TO_DOUBLE: a bad value fails the query instead of becoming NULL
        cols.append(f"CAST(NULLIF(TRIM(\"{raw_name(h)}\"), '') AS DOUBLE) AS \"{out}\"")
    body = ",\n    ".join(cols)
    return f"CREATE VIEW clean.lab_results AS\nSELECT\n    {body}\nFROM raw.lab_results_raw"


def run_checks(con, header):
    results = []

    def check(label, sql_fn, expected):
        try:
            actual = sql_fn()
        except duckdb.Error as e:
            results.append(False)
            print(f"  [FAIL] {label}: {e}")
            return
        ok = actual == expected
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {actual}"
              + ("" if ok else f" (expected {expected})"))

    def one(sql):
        return con.execute(sql).fetchone()[0]

    def rows(sql):
        return con.execute(sql).fetchall()

    print("Load checks (raw table)")
    check("Rows", lambda: one("SELECT COUNT(*) FROM raw.lab_results_raw"), 1005)
    check("Unique batches",
          lambda: one('SELECT COUNT(DISTINCT "BATCH") FROM raw.lab_results_raw'), 1005)
    check("Product codes",
          lambda: one('SELECT COUNT(DISTINCT "CODE") FROM raw.lab_results_raw'), 25)
    check("Start months",
          lambda: one('SELECT COUNT(DISTINCT "START_MONTH") FROM raw.lab_results_raw'), 29)
    stray = " + ".join(f'COUNT(*) FILTER (WHERE contains("{raw_name(h)}", chr(13)))'
                       for h in header)
    check("Cells with a stray carriage return",
          lambda: one(f"SELECT {stray} FROM raw.lab_results_raw"), 0)

    print("View checks (clean view)")
    measurements = [h for h in header if h.lower() not in LABELS]
    check("Measurement columns", lambda: len(measurements), EXPECTED_MEASUREMENTS)
    check("Every value converts strictly",
          lambda: len(rows("SELECT * FROM clean.lab_results")), 1005)
    check("View rows match raw",
          lambda: one("SELECT COUNT(*) FROM clean.lab_results"),
          one("SELECT COUNT(*) FROM raw.lab_results_raw"))
    check("Duplicate batch IDs",
          lambda: one('SELECT COUNT(*) - COUNT(DISTINCT "BATCH") FROM clean.lab_results'), 0)
    check("Months that failed to parse",
          lambda: one('SELECT COUNT(*) FROM clean.lab_results WHERE "START_MONTH" IS NULL'), 0)
    check("Production period",
          lambda: rows('SELECT strftime(MIN("START_MONTH"), \'%Y-%m\'), '
                       'strftime(MAX("START_MONTH"), \'%Y-%m\') FROM clean.lab_results')[0],
          ("2018-11", "2021-04"))
    check("Strength codes that failed to map",
          lambda: one('SELECT COUNT(*) FROM clean.lab_results WHERE "STRENGTH" IS NULL'), 0)
    check("Batches per strength",
          lambda: dict(rows('SELECT "STRENGTH", COUNT(*) FROM clean.lab_results GROUP BY 1')),
          {"5 mg": 249, "10 mg": 213, "20 mg": 445, "40 mg": 98})
    check("API sources with missing API results",
          lambda: [r[0] for r in rows(
              'SELECT DISTINCT TRIM("API_CODE") FROM clean.lab_results '
              'WHERE "API_TOTAL_IMPURITIES" IS NULL OR "API_L_IMPURITY" IS NULL ORDER BY 1')],
          ["3"])
    check("Missing tablet weights by API source",
          lambda: dict(rows('SELECT TRIM("API_CODE"), COUNT(*) FROM clean.lab_results '
                            'WHERE "TBL_MIN_WEIGHT" IS NULL GROUP BY 1')),
          {"3": 8, "4": 2})
    check("Dissolution average, min, max",
          lambda: rows('SELECT ROUND(AVG("DISSOLUTION_AV"), 2), MIN("DISSOLUTION_AV"), '
                       'ROUND(MAX("DISSOLUTION_AV"), 2) FROM clean.lab_results')[0],
          (90.65, 82.5, 102.67))
    return results


def main():
    csv_path = find_csv()
    header = read_header(csv_path)
    print(f"Source: {csv_path.name}, {len(header)} columns")
    if len(header) != EXPECTED_COLUMNS:
        sys.exit(f"Expected {EXPECTED_COLUMNS} columns, found {len(header)}. "
                 "Stopping before anything is built.")

    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir()
    scratch_db = SCRATCH / DB_NAME
    src = str(csv_path).replace("'", "''")
    reader = f"read_csv('{src}', delim=';', header=true, all_varchar=true)"

    results = []
    con = duckdb.connect(str(scratch_db))
    try:
        # Dry run: parse the whole file without storing anything
        dry_rows = con.execute(f"SELECT COUNT(*) FROM {reader}").fetchone()[0]
        print(f"Dry run: {dry_rows} rows parsed, nothing stored yet")

        con.execute("CREATE SCHEMA raw")
        con.execute("CREATE SCHEMA clean")
        con.execute(raw_table_sql(header, reader))
        loaded = con.execute("SELECT COUNT(*) FROM raw.lab_results_raw").fetchone()[0]

        # DuckDB has no LAST_ALTERED, so the load time is logged for the app's header
        con.execute("CREATE TABLE raw.load_log "
                    "(loaded_at TIMESTAMP, source_file VARCHAR, row_count BIGINT)")
        con.execute("INSERT INTO raw.load_log VALUES (?, ?, ?)",
                    [datetime.now(timezone.utc).replace(tzinfo=None), csv_path.name, loaded])

        con.execute(clean_view_sql(header))
        results = run_checks(con, header)
        con.execute("CHECKPOINT")
    except duckdb.Error as e:
        print(f"Build stopped: {e}")
        results.append(False)
    finally:
        con.close()

    if not results or not all(results):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        sys.exit("Build failed. The existing database was left untouched.")

    os.replace(scratch_db, DB_PATH)
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"All {len(results)} checks passed. Built {DB_PATH.name}")


if __name__ == "__main__":
    main()
