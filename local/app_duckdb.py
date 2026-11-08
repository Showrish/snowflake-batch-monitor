"""Run the original Batch Monitor app on DuckDB, without editing it.

app/batch_monitor_app.py stays exactly as it ran in Streamlit in Snowflake.
This launcher registers a stand-in for snowflake.snowpark.context, so the app's
own import line gets the DuckDB session from local_session.py, then runs the
app file unchanged. If the database is missing or older than the build script or
Laboratory.csv (for example after a fresh deploy or a push), it first reruns the same
build and checks as local/build_duckdb.py.

Usage:
    python local/build_duckdb.py      (optional, the launcher builds if needed)
    streamlit run local/app_duckdb.py
"""
import runpy
import sys
import types
from pathlib import Path

import streamlit as st

import local_session

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app" / "batch_monitor_app.py"
INPUTS = [Path(__file__).with_name("build_duckdb.py"), REPO / "Laboratory.csv"]


def database_is_stale():
    db = local_session.DB_PATH
    if not db.exists():
        return True
    built = db.stat().st_mtime
    return any(p.exists() and p.stat().st_mtime > built for p in INPUTS)


def ensure_database():
    """Rebuild when the database is missing or older than its inputs."""
    if not database_is_stale():
        return
    with local_session.BUILD_LOCK:
        if database_is_stale():  # another session may have rebuilt it while we waited
            import build_duckdb
            build_duckdb.main()  # same load and checks as running it by hand
            local_session.reset()


try:
    ensure_database()
except SystemExit as e:
    st.error(f"Data build failed: {e}")
    st.stop()

# Stand-in for the Snowpark module the app imports
context = types.ModuleType("snowflake.snowpark.context")
context.get_active_session = local_session.get_active_session
for name in ("snowflake", "snowflake.snowpark"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["snowflake.snowpark.context"] = context

runpy.run_path(str(APP), run_name="__main__")
