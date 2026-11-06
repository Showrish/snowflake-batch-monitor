"""DuckDB stand-in for Snowflake's session, so the same app runs outside Snowflake.

Inside Streamlit in Snowflake, get_active_session() returns a Snowpark session.
local/app_duckdb.py hands the app this module's version instead, which supports
the same calls the app already makes: session.sql(query).to_pandas() and .collect().

The database is opened read-only, the local version of the read-only role.
"""
import os
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(os.environ.get(
    "BATCH_MONITOR_DB",
    Path(__file__).resolve().parent.parent / "batch_monitor.duckdb"))

# DuckDB has no LAST_ALTERED, so the build script logs the load time instead
LOAD_TIME_SQL = "SELECT MAX(loaded_at) AS LAST_ALTERED FROM batch_monitor.raw.load_log"


class Row(dict):
    """Acts like a Snowpark Row: row["N"] or row[0]."""

    def __init__(self, names, values):
        super().__init__(zip(names, values))
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        for name in self:
            if name.upper() == str(key).upper():
                return super().__getitem__(name)
        if len(self._values) == 1:  # a one-value row answers to any alias
            return self._values[0]
        raise KeyError(key)


class _Result:
    def __init__(self, con, query):
        self._con = con
        self._is_load_time = "LAST_ALTERED" in query.upper()
        self._query = LOAD_TIME_SQL if self._is_load_time else query

    def to_pandas(self):
        cur = self._con.cursor()
        try:
            rel = cur.sql(self._query)
            names, kinds = rel.columns, [str(t) for t in rel.types]
            df = rel.df()
        finally:
            cur.close()
        for name, kind in zip(names, kinds):
            if kind == "DATE":  # Snowpark returns plain dates here, not timestamps
                df[name] = pd.to_datetime(df[name]).dt.date
            elif self._is_load_time and kind.startswith("TIMESTAMP"):
                df[name] = pd.to_datetime(df[name]).dt.tz_localize("UTC")
        return df

    def collect(self):
        cur = self._con.cursor()
        try:
            rel = cur.sql(self._query)
            names = rel.columns
            fetched = rel.fetchall()
        finally:
            cur.close()
        out = []
        for values in fetched:
            if self._is_load_time:
                values = [pd.Timestamp(v).tz_localize("UTC") if v is not None else None
                          for v in values]
            out.append(Row(names, values))
        return out


class LocalSession:
    def __init__(self, path):
        self._con = duckdb.connect(str(path), read_only=True)

    def sql(self, query):
        return _Result(self._con, query)

    def table(self, name):
        return _Result(self._con, f"SELECT * FROM {name}")


_session = None


def get_active_session():
    global _session
    if _session is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(
                f"{DB_PATH.name} not found. Build it first with: python local/build_duckdb.py")
        _session = LocalSession(DB_PATH)
    return _session
