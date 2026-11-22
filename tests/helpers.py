"""Shared helpers for the Batch Monitor tests.

The app file runs Streamlit and asks Snowflake for a session at import time, so the
tests never import it. load_app() runs only its imports, constants and functions,
which lets the tests call the real payload, page and check code directly.
"""
import ast
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
APP_FILE = REPO / "app" / "batch_monitor_app.py"
SKIPPED_PACKAGES = {"streamlit", "snowflake"}


def load_app():
    """Return the app's constants and functions, without running its Streamlit page."""
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if all(a.name.split(".")[0] not in SKIPPED_PACKAGES for a in node.names):
                keep.append(node)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in SKIPPED_PACKAGES:
                keep.append(node)
        elif isinstance(node, ast.FunctionDef):
            keep.append(node)
        elif isinstance(node, ast.Assign) and not any(isinstance(n, ast.Call) for n in ast.walk(node.value)):
            keep.append(node)  # constants only, never the session or data loading calls
    namespace = {"__name__": "batch_monitor_app_under_test"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(APP_FILE), "exec"), namespace)
    return namespace


def make_batches(code, values, attr="DISSOLUTION_AV", start_seq=1, api_lot="L1", start=date(2019, 1, 1)):
    """One row per batch for a product code, in production order, with every column the page reads."""
    rows = []
    for i, v in enumerate(values):
        seq = start_seq + i
        row = {
            "BATCH": str(seq), "BATCH_SEQ": seq, "PRODUCT_CODE": code, "STRENGTH": "10 mg",
            "START_MONTH": pd.Timestamp(start) + pd.DateOffset(months=i // 10),
            "API_CODE": "1", "API_BATCH": api_lot, "LACTOSE_BATCH": "X1", "SMCC_BATCH": "S1", "STARCH_BATCH": "T1",
            "API_TOTAL_IMPURITIES": 0.1, "API_L_IMPURITY": 0.01, "TBL_MIN_WEIGHT": 100.0,
            "DISSOLUTION_AV": 90.0, "DISSOLUTION_MIN": 85.0, "IMPURITIES_TOTAL": 0.2,
            "IMPURITY_O": 0.05, "IMPURITY_L": 0.05, "RESIDUAL_SOLVENT": 0.1,
        }
        row[attr] = v
        rows.append(row)
    return pd.DataFrame(rows)


def render(app, df):
    """The full HTML page the app would show for this data."""
    return app["build_page"](df, len(df), "test", datetime(2026, 11, 22, tzinfo=timezone.utc), None)


def launch_browser(playwright):
    """Chrome comes preinstalled on GitHub's runners. Elsewhere, fall back to Playwright's Chromium."""
    try:
        return playwright.chromium.launch(channel="chrome")
    except Exception:
        return playwright.chromium.launch()
