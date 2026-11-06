"""Run the original Batch Monitor app on DuckDB, without editing it.

app/batch_monitor_app.py stays exactly as it ran in Streamlit in Snowflake.
This launcher registers a stand-in for snowflake.snowpark.context, so the app's
own import line gets the DuckDB session from local_session.py, then runs the
app file unchanged. If the database isn't built yet (for example on a fresh
deploy), it first runs the same build and checks as local/build_duckdb.py.

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

APP = Path(__file__).resolve().parent.parent / "app" / "batch_monitor_app.py"


@st.cache_resource(show_spinner=False)
def ensure_database():
    """Build the database once per server start if it's missing."""
    if not local_session.DB_PATH.exists():
        import build_duckdb
        build_duckdb.main()  # same load and checks as running it by hand
    return True


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
