# Batch performance monitor
# Streamlit in Snowflake application over BATCH_MONITOR.CLEAN.LAB_RESULTS.
# Python reads the data with read-only queries, then hands it to a custom HTML/CSS/JS
# dashboard. Everything is inline because Snowflake blocks external scripts, styles and fonts.

import html
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from snowflake.snowpark.context import get_active_session

APP_OWNER = "Showrish Reddy"
SOURCE_VIEW = "BATCH_MONITOR.CLEAN.LAB_RESULTS"
RAW_TABLE = "BATCH_MONITOR.RAW.LAB_RESULTS_RAW"
MIN_BATCHES = 10        # fewer batches than this gives unreliable control limits
FRAME_HEIGHT = 1420     # fits every view without inner scrolling at typical desktop widths

QUALITY = [   # display name, column, decimals shown
    ("Dissolution, average", "DISSOLUTION_AV", 2),
    ("Dissolution, minimum", "DISSOLUTION_MIN", 2),
    ("Total impurities", "IMPURITIES_TOTAL", 3),
    ("Impurity O", "IMPURITY_O", 3),
    ("Impurity L", "IMPURITY_L", 3),
    ("Residual solvent", "RESIDUAL_SOLVENT", 3),
]
MATERIALS = [   # display name, lot column
    ("API", "API_BATCH"),
    ("Lactose", "LACTOSE_BATCH"),
    ("Silicified microcrystalline cellulose", "SMCC_BATCH"),
    ("Starch", "STARCH_BATCH"),
]
ROW_COLS = ["BATCH", "BATCH_SEQ", "PRODUCT_CODE", "STRENGTH", "MONTH", "MONTH_KEY",
            "API_CODE", "API_BATCH", "LACTOSE_BATCH", "SMCC_BATCH", "STARCH_BATCH"] + [c for _, c, _ in QUALITY]


def load_data(session):
    """Read-only queries. Repeat runs are served from Snowflake's result cache."""
    df = session.sql(f"SELECT * FROM {SOURCE_VIEW}").to_pandas()
    raw_rows = int(session.sql(f"SELECT COUNT(*) AS N FROM {RAW_TABLE}").collect()[0]["N"])
    modified = session.sql(
        "SELECT CONVERT_TIMEZONE('UTC', LAST_ALTERED)::TIMESTAMP_NTZ AS T "
        "FROM BATCH_MONITOR.INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'RAW' AND TABLE_NAME = 'LAB_RESULTS_RAW'"
    ).collect()
    raw_modified = f'{modified[0]["T"]:%Y-%m-%d %H:%M} UTC' if modified else "Unavailable"
    return df, raw_rows, raw_modified


def integrity_checks(df, raw_rows):
    """Each check has an expected value fixed in advance."""
    checks = [
        ("Record count reconciliation", "Every raw record reaches the clean view", raw_rows, len(df)),
        ("Batch ID uniqueness", "No batch ID appears more than once", 0, int(df["BATCH"].duplicated().sum())),
        ("Start month conversion", "Every month label converts to a date", 0, int(df["START_MONTH"].isna().sum())),
        ("Strength label mapping", "Every strength label maps to a standard value", 0, int(df["STRENGTH"].isna().sum())),
    ]
    return [(name, what, exp, obs, exp == obs) for name, what, exp, obs in checks]


def header_html(df, checks, raw_modified, generated):
    passed = sum(ok for *_, ok in checks)
    dot = "dot" if passed == len(checks) else "dot fail"
    first, last = df["START_MONTH"].min(), df["START_MONTH"].max()
    return f"""
<header class="glass hdr">
  <div class="hdr-top">
    <div>
      <h1>Batch performance monitor</h1>
      <p class="sub">Film-coated tablets made by direct compression. {len(df):,} anonymized production
      batches across {df["PRODUCT_CODE"].nunique()} product codes.</p>
    </div>
    <span class="chip"><span class="{dot}"></span>Data integrity: {passed} of {len(checks)} checks passed</span>
  </div>
  <div class="meta">
    <div><div class="lbl">Data source</div><div class="val"><code>{SOURCE_VIEW}</code></div></div>
    <div><div class="lbl">Production period</div><div class="val">{first:%b %Y} to {last:%b %Y}</div></div>
    <div><div class="lbl">Raw table last modified</div><div class="val">{raw_modified}</div></div>
    <div><div class="lbl">Report generated</div><div class="val">{generated:%Y-%m-%d %H:%M} UTC</div></div>
  </div>
</header>"""


def integrity_html(df, checks):
    def num(v, gap=False):
        cls = " zero" if v == 0 else (" gap" if gap else "")
        return f'<td class="num{cls}">{v:,}</td>'

    check_rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td class='muted'>{html.escape(w)}</td>{num(e)}{num(o)}"
        f"<td><span class='pill {'pass' if ok else 'fail'}'>{'Pass' if ok else 'Fail'}</span></td></tr>"
        for n, w, e, o, ok in checks
    )
    gaps = df.groupby("API_CODE").agg(
        batches=("BATCH", "size"),
        imp=("API_TOTAL_IMPURITIES", lambda s: int(s.isna().sum())),
        imp_l=("API_L_IMPURITY", lambda s: int(s.isna().sum())),
        weight=("TBL_MIN_WEIGHT", lambda s: int(s.isna().sum())),
    ).reset_index()
    gap_rows = "".join(
        f"<tr><td>Source {html.escape(str(r.API_CODE))}</td>{num(r.batches)}{num(r.imp, True)}{num(r.imp_l, True)}{num(r.weight, True)}</tr>"
        for r in gaps.itertuples()
    )
    gap_sources = ", ".join(str(s) for s in gaps.loc[gaps["imp"] > 0, "API_CODE"])
    no_weight = int(df["TBL_MIN_WEIGHT"].isna().sum())
    shared_lots = int((df.groupby("API_BATCH")["API_CODE"].nunique() > 1).sum())
    return f"""
<div class="glass panel">
  <div class="panel-head"><h2>Integrity checks</h2><p class="hint">Run on every load, against expected values fixed in advance.</p></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Check</th><th>What it verifies</th><th class="num">Expected</th><th class="num">Observed</th><th>Result</th></tr></thead>
    <tbody>{check_rows}</tbody>
  </table></div>
</div>
<div class="grid-2">
  <div class="glass panel">
    <div class="panel-head"><h2>Missing results by API source</h2><p class="hint">Gaps are reported, not filled in.</p></div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>API source</th><th class="num">Batches</th><th class="num">API total impurities</th><th class="num">API impurity L</th><th class="num">Tablet weight</th></tr></thead>
      <tbody>{gap_rows}</tbody>
    </table></div>
  </div>
  <div class="glass panel">
    <div class="panel-head"><h2>Observations</h2></div>
    <ul class="obs">
      <li>Missing API test results are confined to API source {gap_sources}.</li>
      <li>{no_weight} batches have no tablet weight recorded. The dataset's publication does not mention this gap.</li>
      <li>{shared_lots} API lot numbers appear under more than one API source, so an API lot is identified by source and lot number together.</li>
    </ul>
  </div>
</div>
<div class="glass panel">
  <div class="panel-head"><h2>Data lineage</h2><p class="hint">How a record gets from the source file to this screen.</p></div>
  <div class="flow">
    <div class="step"><div class="n">1</div><div class="t">Source file received</div><div class="d">Laboratory.csv, semicolon-delimited, one row per batch</div></div>
    <div class="step"><div class="n">2</div><div class="t">Landed unchanged</div><div class="d"><code>RAW.LAB_RESULTS_RAW</code>, every column stored as text</div></div>
    <div class="step"><div class="n">3</div><div class="t">Typed and standardized</div><div class="d"><code>CLEAN.LAB_RESULTS</code> view. The raw table is never edited</div></div>
    <div class="step"><div class="n">4</div><div class="t">Reviewed here</div><div class="d">Read-only queries from this application</div></div>
  </div>
</div>"""


def payload(df):
    counts = df["PRODUCT_CODE"].value_counts()
    rows = []
    for rec in df[ROW_COLS].itertuples(index=False):
        row = []
        for col, val in zip(ROW_COLS, rec):
            if col == "BATCH_SEQ":
                row.append(int(val))
            elif col in {c for _, c, _ in QUALITY}:
                row.append(None if pd.isna(val) else float(val))
            else:
                row.append(None if pd.isna(val) else str(val))
        rows.append(row)
    data = {
        "cols": ROW_COLS,
        "rows": rows,
        "codes": [[str(c), int(n)] for c, n in counts.items() if n >= MIN_BATCHES],
        "attrs": [list(a) for a in QUALITY],
        "materials": [list(m) for m in MATERIALS],
    }
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def build_page(df, raw_rows, raw_modified, generated):
    df = df.copy()
    df["START_MONTH"] = pd.to_datetime(df["START_MONTH"])
    df["MONTH"] = df["START_MONTH"].dt.strftime("%b %Y")
    df["MONTH_KEY"] = df["START_MONTH"].dt.strftime("%Y-%m")
    checks = integrity_checks(df, raw_rows)
    footer = (
        '<footer class="foot">Source data: Žagar J. and Mihelič J., Big data collection in pharmaceutical '
        "manufacturing and its use for product quality predictions, Scientific Data (2022), "
        f"doi:10.1038/s41597-022-01203-x. Prepared by {html.escape(APP_OWNER)}.</footer>"
    )
    return (PAGE.replace("__HEADER__", header_html(df, checks, raw_modified, generated))
                .replace("__INTEGRITY__", integrity_html(df, checks))
                .replace("__FOOTER__", footer)
                .replace("__DATA__", payload(df)))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#0A0E17;--panel:rgba(255,255,255,.035);--panel-2:rgba(255,255,255,.06);
  --line:rgba(255,255,255,.08);--line-2:rgba(255,255,255,.15);
  --text:#E6ECF5;--text-2:#A3AFC2;--text-3:#6F7B8F;
  --accent:#7CB8FF;--accent-soft:rgba(124,184,255,.14);
  --signal:#FF7A6B;--signal-soft:rgba(255,122,107,.15);
  --pass:#43D398;--pass-soft:rgba(67,211,152,.15);
  --warn:#F2C35B;--warn-soft:rgba(242,195,91,.10);
  --limit:#8A96AA;
  --font:"Segoe UI Variable Text","Segoe UI",-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"Cascadia Mono",Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;color:var(--text);font-family:var(--font);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
body{min-height:100vh;background:
  radial-gradient(900px 480px at 6% -10%,rgba(64,132,214,.22),transparent 62%),
  radial-gradient(760px 520px at 104% 108%,rgba(38,166,154,.13),transparent 60%),var(--bg)}
.wrap{max-width:1380px;margin:0 auto;padding:24px 28px 30px}
code{font-family:var(--mono);font-size:12.5px;color:var(--text-2)}
h1,h2{margin:0}
.glass{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}

.hdr{padding:22px 24px 14px}
.hdr-top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}
.hdr h1{font-size:26px;font-weight:600;letter-spacing:-.015em;line-height:1.2;margin-bottom:5px}
.sub{margin:0;color:var(--text-2);max-width:72ch}
.chip{display:inline-flex;align-items:center;gap:9px;padding:7px 13px;border-radius:999px;
  border:1px solid var(--line-2);background:var(--panel-2);font-size:13px;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:var(--pass);box-shadow:0 0 0 3px var(--pass-soft)}
.dot.fail{background:var(--signal);box-shadow:0 0 0 3px var(--signal-soft)}
.meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px;border-top:1px solid var(--line)}
.meta>div{padding:12px 16px 4px 0}
.meta>div+div{padding-left:16px;border-left:1px solid var(--line)}
.lbl{font-size:12px;color:var(--text-3);margin-bottom:3px}
.val{font-variant-numeric:tabular-nums}
.use{font-size:12.5px;color:var(--text-3);margin:12px 4px 18px}

.tabs{display:inline-flex;gap:4px;padding:4px;border:1px solid var(--line);border-radius:999px;
  background:rgba(255,255,255,.02);margin-bottom:16px}
.tab{appearance:none;border:0;background:transparent;color:var(--text-2);font:inherit;font-size:13.5px;
  padding:8px 18px;border-radius:999px;cursor:pointer;transition:background .15s,color .15s}
.tab:hover{color:var(--text)}
.tab[aria-selected="true"]{background:var(--accent-soft);color:var(--accent)}
.tab:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.blocked{color:var(--warn);font-size:13px;margin:0 4px 16px}

.stack{display:grid;gap:16px}
.stack[hidden]{display:none}
.panel{padding:18px 20px}
.panel-head{margin-bottom:12px}
.panel-head h2,.chart-head h2{font-size:15px;font-weight:600}
.hint{color:var(--text-3);font-size:12.5px;margin:2px 0 0}
.grid-2{display:grid;grid-template-columns:1.25fr 1fr;gap:16px}
.trend-grid{display:grid;grid-template-columns:minmax(0,2.15fr) minmax(300px,1fr);gap:16px;align-items:start}
.flags .tbl-wrap{overflow:auto}

.controls{display:flex;flex-wrap:wrap;gap:14px 18px;align-items:flex-end}
.field{display:grid;gap:6px}
.field label{font-size:12px;color:var(--text-3)}
select{appearance:none;-webkit-appearance:none;font:inherit;color:var(--text);min-width:250px;
  background-color:rgba(255,255,255,.045);border:1px solid var(--line-2);border-radius:10px;
  padding:9px 38px 9px 12px;cursor:pointer;background-repeat:no-repeat;background-position:right 13px center;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 4.5 6 8l3.5-3.5' fill='none' stroke='%23A3AFC2' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")}
select:hover{border-color:rgba(255,255,255,.25)}
select option{background:#141A26;color:var(--text)}

.kpis{display:flex;flex-wrap:wrap;margin-top:18px;border-top:1px solid var(--line)}
.kpi{padding:14px 30px 2px 0;margin-right:30px;border-right:1px solid var(--line)}
.kpi:last-child{border-right:0;margin-right:0}
.kpi .v{font-size:26px;font-weight:600;letter-spacing:-.015em;line-height:1.2;font-variant-numeric:tabular-nums}
.kpi .v.signal{color:var(--signal)}
.kpi .v.quiet{font-size:18px;color:var(--text-2);padding-top:6px}

.banner{padding:12px 16px;border-radius:12px;font-size:13.5px;border:1px solid;line-height:1.55}
.banner.warn{background:var(--warn-soft);border-color:rgba(242,195,91,.32);color:#F5D88E}
.banner.info{background:var(--accent-soft);border-color:rgba(124,184,255,.32);color:#C4DDFF}

.chart-head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:4px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--text-2)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend[hidden]{display:none}
.sw{width:9px;height:9px;border-radius:50%;display:inline-block}
.sw.ln{width:16px;height:0;border-radius:0;border-top:1.5px solid var(--limit)}
.sw.dl{width:16px;height:0;border-radius:0;border-top:1.5px dashed var(--limit)}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto}
.chart .empty{color:var(--text-3);font-size:13px;padding:22px 0}
.divider{height:1px;background:var(--line);margin:16px 0 14px}
.tip{position:absolute;left:0;top:0;pointer-events:none;background:#121826;border:1px solid var(--line-2);
  border-radius:10px;padding:8px 11px;font-size:12.5px;line-height:1.5;white-space:nowrap;
  box-shadow:0 10px 28px rgba(0,0,0,.4);opacity:0;transition:opacity .12s;z-index:5}
.tip.show{opacity:1}
.tip .k{color:var(--text-3)}
.tip .big{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums}
.tip .sig{color:var(--signal);margin-top:2px}

.tbl-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}
.tbl-wrap.scroll{max-height:330px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{position:sticky;top:0;background:#111726;color:var(--text-3);font-weight:500;text-align:left;
  padding:10px 14px;border-bottom:1px solid var(--line);white-space:nowrap;z-index:1}
td{padding:9px 14px;border-bottom:1px solid rgba(255,255,255,.05)}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:rgba(255,255,255,.025)}
th.num,td.num{text-align:right}
td.zero{color:var(--text-3)}
td.muted{color:var(--text-2)}
td.hot{color:var(--signal)}
td.gap{color:var(--warn)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:500}
.pill.pass{background:var(--pass-soft);color:var(--pass)}
.pill.fail{background:var(--signal-soft);color:var(--signal)}
.count{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;font-size:12px;
  font-weight:500;background:var(--signal-soft);color:var(--signal);vertical-align:1px}
.none{color:var(--text-2);margin:0}

.obs{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.obs li{position:relative;padding-left:18px;color:var(--text-2);line-height:1.55}
.obs li::before{content:"";position:absolute;left:0;top:.6em;width:6px;height:6px;border-radius:50%;background:var(--accent)}
.flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
.step{position:relative;padding:4px 18px 2px 0}
.step .n{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:12.5px;font-weight:600;
  background:var(--accent-soft);color:var(--accent);margin-bottom:10px;position:relative;z-index:1}
.step::after{content:"";position:absolute;top:18px;left:38px;right:10px;height:1px;background:var(--line-2)}
.step:last-child::after{display:none}
.step .t{font-weight:600;font-size:13.5px}
.step .d{color:var(--text-2);font-size:12.5px;margin-top:3px;line-height:1.5}

details{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
summary{cursor:pointer;color:var(--text-2);font-size:13px;list-style:none;display:inline-flex;align-items:center;gap:8px}
summary::-webkit-details-marker{display:none}
summary::before{content:"";width:6px;height:6px;border-right:1.5px solid var(--accent);border-bottom:1.5px solid var(--accent);
  transform:rotate(-45deg);transition:transform .15s}
details[open] summary::before{transform:rotate(45deg)}
details p{color:var(--text-2);font-size:13px;line-height:1.7;max-width:92ch;margin:10px 0 0}
.foot{margin:22px 4px 0;color:var(--text-3);font-size:12px;line-height:1.6;max-width:125ch}

@media (max-width:1100px){.trend-grid{grid-template-columns:1fr}}
@media (max-width:1000px){.grid-2{grid-template-columns:1fr}.meta{grid-template-columns:repeat(2,minmax(0,1fr))}
  .meta>div+div{border-left:0;padding-left:0}.flow{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.step::after{display:none}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head>
<body><div class="wrap">
__HEADER__
<p class="use">Intended use: demonstration of batch data review on a public, anonymized dataset. This is not a validated system and must not be used for GMP decisions.</p>

<div class="tabs" role="tablist" aria-label="Views">
  <button class="tab" role="tab" aria-selected="true" aria-controls="integrity" data-tab="integrity">Data integrity</button>
  <button class="tab" role="tab" aria-selected="false" aria-controls="trend" data-tab="trend">Process trending</button>
  <button class="tab" role="tab" aria-selected="false" aria-controls="lots" data-tab="lots">Material genealogy</button>
</div>
<p class="blocked" id="js-note">Process trending and material genealogy need browser scripts, which this environment blocked.</p>

<section id="integrity" class="stack" role="tabpanel">__INTEGRITY__</section>

<section id="trend" class="stack" role="tabpanel" hidden>
  <div class="glass panel">
    <div class="controls">
      <div class="field"><label for="f-code">Product code</label><select id="f-code"></select></div>
      <div class="field"><label for="f-attr">Quality attribute</label><select id="f-attr"></select></div>
    </div>
    <div class="kpis" id="t-kpis"></div>
  </div>
  <div id="t-banner" hidden></div>
  <div class="trend-grid">
  <div class="glass panel" id="t-charts">
    <div class="chart-head">
      <div><h2>Individual values</h2><p class="hint" id="t-sub"></p></div>
      <div class="legend" id="t-legend">
        <span><i class="sw" style="background:var(--accent)"></i>Within limits</span>
        <span><i class="sw" style="background:var(--signal)"></i>Beyond limits</span>
        <span><i class="sw ln"></i>Mean</span>
        <span><i class="sw dl"></i>Control limit</span>
      </div>
    </div>
    <div class="chart" id="c-i"></div>
    <div class="divider"></div>
    <div class="chart-head"><div><h2>Moving range</h2><p class="hint">Change from the previous batch</p></div></div>
    <div class="chart" id="c-mr"></div>
    <details><summary>How the limits are calculated</summary><p>Individuals and moving range (I-MR) chart for one product
    code in production order. Control limits are the process mean ± 3σ, where σ is the average moving range divided by 1.128.
    The moving range upper limit is 3.267 times the average moving range. A point beyond a control limit is flagged for review.
    Control limits describe the process's own variation and are not specification limits. Heavily repeated values, such as
    results recorded at a reporting limit, make these limits unreliable, and the app flags when that applies. Every batch in
    this dataset met its specification, and the source data does not include specification limits, so capability indices are
    not calculated.</p></details>
  </div>
  <div class="glass panel flags" id="t-flags"></div>
  </div>
</section>

<section id="lots" class="stack" role="tabpanel" hidden>
  <div class="glass panel">
    <div class="controls">
      <div class="field"><label for="f-mat">Material</label><select id="f-mat"></select></div>
      <div class="field"><label for="f-lot">Lot</label><select id="f-lot"></select></div>
    </div>
    <div class="kpis" id="l-kpis"></div>
  </div>
  <div class="glass panel" id="l-table"></div>
</section>
__FOOTER__
</div>

<script id="bpm-data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var note = document.getElementById("js-note");
  if (note) note.remove();

  var D = JSON.parse(document.getElementById("bpm-data").textContent);
  var I = {};
  D.cols.forEach(function (c, i) { I[c] = i; });
  var R = D.rows;
  var NS = "http://www.w3.org/2000/svg";

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(v, dp) { return (v === null || v === undefined || isNaN(v)) ? "–" : v.toFixed(dp); }
  function option(value, label) { var o = document.createElement("option"); o.value = value; o.textContent = label; return o; }
  function kpis(el, items) {
    el.innerHTML = items.map(function (k) {
      return '<div class="kpi"><div class="lbl">' + esc(k[0]) + '</div><div class="v ' + (k[2] || "") + '">' + esc(k[1]) + "</div></div>";
    }).join("");
  }

  /* ---------- Tabs ---------- */
  var shown = { integrity: true };
  document.querySelectorAll(".tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab").forEach(function (b) { b.setAttribute("aria-selected", b === btn ? "true" : "false"); });
      ["integrity", "trend", "lots"].forEach(function (s) { $(s).hidden = s !== id; });
      if (id === "trend") renderTrend();
      if (id === "lots" && !shown.lots) renderLots();
      shown[id] = true;
    });
  });

  /* ---------- I-MR statistics ---------- */
  function series(code, key) {
    var k = I[key];
    var pts = R.filter(function (r) { return r[I.PRODUCT_CODE] === code && r[k] !== null; })
      .sort(function (a, b) { return a[I.BATCH_SEQ] - b[I.BATCH_SEQ]; })
      .map(function (r, i) { return { x: i + 1, v: r[k], batch: r[I.BATCH], month: r[I.MONTH] }; });
    var n = pts.length, sum = 0, mrSum = 0;
    pts.forEach(function (p, i) {
      sum += p.v;
      p.mr = i === 0 ? null : Math.abs(p.v - pts[i - 1].v);
      if (i > 0) mrSum += p.mr;
    });
    var mean = sum / n, mrBar = n > 1 ? mrSum / (n - 1) : 0;
    var counts = new Map(), topV = null, topC = 0;
    pts.forEach(function (p) { counts.set(p.v, (counts.get(p.v) || 0) + 1); });
    counts.forEach(function (c, v) { if (c > topC) { topC = c; topV = v; } });
    var s = { pts: pts, n: n, mean: mean, mrBar: mrBar, topV: topV, topShare: n ? topC / n : 0, constant: mrBar === 0 };
    if (!s.constant) {
      s.sigma = mrBar / 1.128;
      s.ucl = mean + 3 * s.sigma;
      s.lcl = mean - 3 * s.sigma;
      s.mrUcl = 3.267 * mrBar;
      pts.forEach(function (p) {
        p.flag = p.v > s.ucl || p.v < s.lcl;
        p.mrFlag = p.mr !== null && p.mr > s.mrUcl;
      });
      s.signals = pts.filter(function (p) { return p.flag; }).length;
    }
    return s;
  }
  window.BPM = { series: series };

  /* ---------- SVG chart ---------- */
  function niceStep(range, count) {
    var raw = range / count, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
  }
  function el(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    for (var a in attrs) e.setAttribute(a, attrs[a]);
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function drawChart(host, cfg) {
    host.innerHTML = "";
    var W = Math.max(host.clientWidth || 0, 360), H = cfg.height;
    var m = { l: 54, r: 92, t: 14, b: cfg.xTitle ? 40 : 26 };
    var pts = cfg.pts;
    var ys = pts.map(function (p) { return p.y; }).concat(cfg.lines.map(function (l) { return l.v; }));
    var yMin = Math.min.apply(null, ys), yMax = Math.max.apply(null, ys);
    if (yMax === yMin) { var d = Math.abs(yMax) * 0.05 || 1; yMin -= d; yMax += d; }
    var pad = (yMax - yMin) * 0.12; yMin -= pad; yMax += pad;
    if (cfg.floorZero) yMin = Math.max(yMin, 0);
    var xMax = Math.max(pts.length ? pts[pts.length - 1].x : 2, 2);
    function X(v) { return m.l + (v - 1) / (xMax - 1) * (W - m.l - m.r); }
    function Y(v) { return m.t + (yMax - v) / (yMax - yMin) * (H - m.t - m.b); }

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": cfg.aria });
    var ys_ = niceStep(yMax - yMin, cfg.yTicks || 5), ydp = Math.max(0, -Math.floor(Math.log10(ys_)));
    for (var t = Math.ceil(yMin / ys_) * ys_; t <= yMax + 1e-12; t += ys_) {
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: "rgba(255,255,255,.06)" }));
      svg.appendChild(el("text", { x: m.l - 10, y: Y(t), "text-anchor": "end", "dominant-baseline": "central",
        fill: "#6F7B8F", "font-size": 11 }, t.toFixed(ydp)));
    }
    var xs_ = Math.max(1, niceStep(xMax - 1, 8));
    for (var xt = 1; xt <= xMax; xt += xs_) {
      svg.appendChild(el("text", { x: X(xt), y: H - m.b + 18, "text-anchor": "middle", fill: "#6F7B8F", "font-size": 11 }, String(Math.round(xt))));
    }
    if (cfg.xTitle) svg.appendChild(el("text", { x: m.l + (W - m.l - m.r) / 2, y: H - 4, "text-anchor": "middle", fill: "#6F7B8F", "font-size": 11 },
      cfg.xTitle));

    cfg.lines.forEach(function (l) {
      svg.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: Y(l.v), y2: Y(l.v), stroke: "#8A96AA",
        "stroke-width": 1.2, "stroke-dasharray": l.dash ? "5 4" : "none", opacity: 0.9 }));
      svg.appendChild(el("text", { x: W - m.r + 8, y: Y(l.v), "dominant-baseline": "central", fill: "#A3AFC2",
        "font-size": 11 }, l.label));
    });

    if (pts.length > 1) {
      var d = pts.map(function (p, i) { return (i ? "L" : "M") + X(p.x).toFixed(1) + " " + Y(p.y).toFixed(1); }).join(" ");
      svg.appendChild(el("path", { d: d, fill: "none", stroke: "#7CB8FF", "stroke-width": 1.4, opacity: 0.45,
        "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    var r = pts.length > 120 ? 2.8 : 3.4;
    pts.forEach(function (p) {
      svg.appendChild(el("circle", { cx: X(p.x), cy: Y(p.y), r: p.flag ? r + 1.1 : r,
        fill: p.flag ? "#FF7A6B" : "#7CB8FF", stroke: p.flag ? "rgba(255,122,107,.35)" : "none", "stroke-width": p.flag ? 4 : 0 }));
    });

    var guide = el("line", { y1: m.t, y2: H - m.b, stroke: "rgba(255,255,255,.18)", "stroke-dasharray": "2 3", visibility: "hidden" });
    var ring = el("circle", { r: 7, fill: "none", stroke: "#E6ECF5", "stroke-width": 1.5, visibility: "hidden" });
    svg.appendChild(guide); svg.appendChild(ring);
    host.appendChild(svg);

    var tip = document.createElement("div");
    tip.className = "tip";
    host.appendChild(tip);

    function hide() { tip.classList.remove("show"); guide.setAttribute("visibility", "hidden"); ring.setAttribute("visibility", "hidden"); }
    svg.addEventListener("mouseleave", hide);
    svg.addEventListener("mousemove", function (ev) {
      if (!pts.length) return;
      var box = svg.getBoundingClientRect(), sx = W / box.width;
      var mx = (ev.clientX - box.left) * sx;
      var best = pts[0], bd = Infinity;
      pts.forEach(function (p) { var dd = Math.abs(X(p.x) - mx); if (dd < bd) { bd = dd; best = p; } });
      var cx = X(best.x), cy = Y(best.y);
      guide.setAttribute("x1", cx); guide.setAttribute("x2", cx); guide.setAttribute("visibility", "visible");
      ring.setAttribute("cx", cx); ring.setAttribute("cy", cy); ring.setAttribute("visibility", "visible");
      tip.innerHTML = cfg.tip(best);
      tip.classList.add("show");
      var px = cx / sx, py = cy / sx, tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.min(Math.max(px - tw / 2, 4), box.width - tw - 4);
      var top = py - th - 14 < 0 ? py + 14 : py - th - 14;
      tip.style.transform = "translate(" + left + "px," + top + "px)";
    });
  }

  /* ---------- Process trending ---------- */
  var fCode = $("f-code"), fAttr = $("f-attr");
  D.codes.forEach(function (c) { fCode.appendChild(option(c[0], c[0] + "  (" + c[1] + " batches)")); });
  D.attrs.forEach(function (a, i) { fAttr.appendChild(option(i, a[0])); });
  fCode.addEventListener("change", renderTrend);
  fAttr.addEventListener("change", renderTrend);

  function renderTrend() {
    var code = fCode.value, a = D.attrs[+fAttr.value], label = a[0], key = a[1], dp = a[2];
    var s = series(code, key);
    $("t-sub").textContent = label + " for product code " + code + ", " + s.n + " batches in production order";
    $("t-legend").hidden = s.constant;
    var banner = $("t-banner");
    if (s.constant) {
      kpis($("t-kpis"), [["Batches", String(s.n)], ["Reported value", fmt(s.topV, dp)], ["Control limits", "Not calculable", "quiet"]]);
      banner.className = "banner info"; banner.hidden = false;
      banner.textContent = "All " + s.n + " results for product code " + code + " are " + fmt(s.topV, dp) +
        ", so control limits can't be calculated. Identical values like this often reflect results recorded at a reporting limit.";
    } else {
      kpis($("t-kpis"), [["Batches", String(s.n)], ["Process mean", fmt(s.mean, dp)], ["Lower control limit", fmt(s.lcl, dp)],
        ["Upper control limit", fmt(s.ucl, dp)], ["Points beyond limits", String(s.signals), s.signals ? "signal" : ""]]);
      if (s.topShare >= 0.5) {
        banner.className = "banner warn"; banner.hidden = false;
        banner.textContent = Math.round(s.topShare * 100) + "% of these results are exactly " + fmt(s.topV, dp) +
          ". Heavily repeated values, often a reporting limit, make control limits unreliable, so treat flagged points with caution.";
      } else { banner.hidden = true; }
    }

    var tipI = function (p) {
      return '<div class="k">Batch ' + esc(p.batch) + '</div><div class="big">' + fmt(p.y, dp) + "</div>" +
        '<div class="k">Started ' + esc(p.month) + "</div>" + (p.flag ? '<div class="sig">Beyond control limits</div>' : "");
    };
    var iLines = s.constant ? [] : [
      { v: s.ucl, label: "UCL " + fmt(s.ucl, dp), dash: true },
      { v: s.mean, label: "Mean " + fmt(s.mean, dp), dash: false },
      { v: s.lcl, label: "LCL " + fmt(s.lcl, dp), dash: true }];
    drawChart($("c-i"), { height: 300, aria: "Individuals chart", lines: iLines, tip: tipI, xTitle: s.constant ? "Batch sequence (production order)" : "",
      pts: s.pts.map(function (p) { return { x: p.x, y: p.v, batch: p.batch, month: p.month, flag: !!p.flag }; }) });

    if (s.constant) {
      $("c-mr").innerHTML = '<p class="empty">Every change from the previous batch is zero.</p>';
    } else {
      var tipMR = function (p) {
        return '<div class="k">Batch ' + esc(p.batch) + '</div><div class="big">' + fmt(p.y, dp) + "</div>" +
          '<div class="k">Change from the previous batch</div>' + (p.flag ? '<div class="sig">Beyond the upper limit</div>' : "");
      };
      drawChart($("c-mr"), { height: 170, aria: "Moving range chart", floorZero: true, tip: tipMR, yTicks: 3, xTitle: "Batch sequence (production order)",
        lines: [{ v: s.mrUcl, label: "UCL " + fmt(s.mrUcl, dp), dash: true }, { v: s.mrBar, label: "Average " + fmt(s.mrBar, dp), dash: false }],
        pts: s.pts.slice(1).map(function (p) { return { x: p.x, y: p.mr, batch: p.batch, month: p.month, flag: p.mrFlag }; }) });
    }

    var flags = $("t-flags"), head = '<div class="panel-head"><h2>Beyond control limits' +
      (s.signals ? '<span class="count">' + s.signals + "</span>" : "") + '</h2><p class="hint">' +
      (s.constant ? "Not applicable for this selection." : s.signals ? "Worth a look, even though every batch met specification."
        : "No batch falls outside the control limits.") + "</p></div>";
    if (s.constant || !s.signals) {
      flags.innerHTML = head;
    } else {
      var rows = s.pts.filter(function (p) { return p.flag; }).map(function (p) {
        var z = (p.v - s.mean) / s.sigma;
        return "<tr><td>" + esc(p.batch) + "</td><td>" + esc(p.month) + '</td><td class="num">' + fmt(p.v, dp) +
          '</td><td class="num hot">' + (z > 0 ? "+" : "−") + Math.abs(z).toFixed(2) + "σ</td></tr>";
      }).join("");
      flags.innerHTML = head + '<div class="tbl-wrap" id="t-flag-wrap"><table><thead><tr><th>Batch</th><th>Month</th>' +
        '<th class="num">Value</th><th class="num">From mean</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
    }
    sizeFlags();
  }

  function sizeFlags() {
    // Match the flagged-batch panel to the charts panel beside it, and let its table scroll inside
    var flags = $("t-flags"), wrap = $("t-flag-wrap");
    var twoCol = getComputedStyle(document.querySelector(".trend-grid")).gridTemplateColumns.split(" ").length > 1;
    if (!twoCol) { flags.style.height = ""; if (wrap) wrap.style.maxHeight = "330px"; return; }
    var h = $("t-charts").offsetHeight;
    flags.style.height = h + "px";
    if (wrap) {
      var offset = wrap.getBoundingClientRect().top - flags.getBoundingClientRect().top;
      wrap.style.maxHeight = Math.max(200, h - offset - 19) + "px";
    }
  }

  /* ---------- Material genealogy ---------- */
  var fMat = $("f-mat"), fLot = $("f-lot");
  D.materials.forEach(function (mm, i) { fMat.appendChild(option(i, mm[0])); });
  function lotKey(r, mat) {
    return mat[0] === "API" ? "Source " + r[I.API_CODE] + ", lot " + r[I.API_BATCH] : "Lot " + r[I[mat[1]]];
  }
  function fillLots() {
    var mat = D.materials[+fMat.value], counts = new Map();
    R.forEach(function (r) { var k = lotKey(r, mat); counts.set(k, (counts.get(k) || 0) + 1); });
    var lots = Array.from(counts.entries()).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0], undefined, { numeric: true }); });
    fLot.innerHTML = "";
    lots.forEach(function (l) { fLot.appendChild(option(l[0], l[0] + "  (" + l[1] + (l[1] === 1 ? " batch)" : " batches)"))); });
  }
  fMat.addEventListener("change", function () { fillLots(); renderLots(); });
  fLot.addEventListener("change", renderLots);
  fillLots();

  function renderLots() {
    var mat = D.materials[+fMat.value], lot = fLot.value;
    var used = R.filter(function (r) { return lotKey(r, mat) === lot; })
      .sort(function (a, b) { return a[I.MONTH_KEY].localeCompare(b[I.MONTH_KEY]) || a[I.BATCH_SEQ] - b[I.BATCH_SEQ]; });
    var codes = new Set(used.map(function (r) { return r[I.PRODUCT_CODE]; }));
    kpis($("l-kpis"), [["Finished batches", String(used.length)], ["Product codes", String(codes.size)],
      ["First use", used.length ? used[0][I.MONTH] : "–"], ["Last use", used.length ? used[used.length - 1][I.MONTH] : "–"]]);
    var body = used.map(function (r) {
      return "<tr><td>" + esc(r[I.BATCH]) + "</td><td>" + esc(r[I.PRODUCT_CODE]) + "</td><td>" + esc(r[I.STRENGTH]) + "</td><td>" +
        esc(r[I.MONTH]) + '</td><td class="num">' + fmt(r[I.DISSOLUTION_AV], 2) + '</td><td class="num">' + fmt(r[I.DISSOLUTION_MIN], 2) +
        '</td><td class="num">' + fmt(r[I.IMPURITIES_TOTAL], 3) + "</td></tr>";
    }).join("");
    var note = mat[0] === "API"
      ? "API lot numbers are reused across API sources, so an API lot is identified by its source and lot number together."
      : "The source data has no supplier field for excipients, so excipient lots are identified by lot number alone.";
    $("l-table").innerHTML = '<div class="panel-head"><h2>Finished batches made with ' + esc(mat[0].toLowerCase() === "api" ? "API" : mat[0].toLowerCase()) +
      " " + esc(lot.charAt(0).toLowerCase() + lot.slice(1)) + '</h2><p class="hint">' + esc(note) + "</p></div>" +
      '<div class="tbl-wrap scroll"><table><thead><tr><th>Batch</th><th>Product code</th><th>Strength</th><th>Start month</th>' +
      '<th class="num">Dissolution, average</th><th class="num">Dissolution, minimum</th><th class="num">Total impurities</th></tr></thead><tbody>' +
      body + "</tbody></table></div>";
  }

  document.querySelector("#t-charts details").addEventListener("toggle", sizeFlags);
  var raf = 0;
  window.addEventListener("resize", function () {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function () { if (!$("trend").hidden) renderTrend(); });
  });
})();
</script>
</body></html>"""


# ---------- Streamlit page: a full-width frame on a matching background
st.set_page_config(layout="wide")
st.markdown(
    "<style>"
    ".stApp,[data-testid='stAppViewContainer']{background:#0A0E17}"
    "[data-testid='stHeader']{background:transparent}"
    ".block-container,[data-testid='stMainBlockContainer']{padding:.5rem 1rem 0;max-width:100%}"
    "</style>",
    unsafe_allow_html=True,
)

session = get_active_session()
data, raw_count, raw_modified_at = load_data(session)
components.html(
    build_page(data, raw_count, raw_modified_at, datetime.now(timezone.utc)),
    height=FRAME_HEIGHT,
    scrolling=True,
)
