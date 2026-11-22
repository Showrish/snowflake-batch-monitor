# Design decisions

Why Batch Monitor is built the way it is. Each entry says what was decided, why, and what it costs.

## Data and integrity

**The raw file is kept exactly as delivered.** `RAW.LAB_RESULTS_RAW` stores every column as text, and nothing in it is ever edited. Conversion only happens later, in the clean view, so no value can be lost or silently changed at load. Trade-off: every query reads through the view's conversions.

**Fixes live in one view, not a second table.** `CLEAN.LAB_RESULTS` trims the runs of spaces that stand for missing values, turns the Slovenian month labels into dates, maps the truncated strength codes to readable labels, and converts every measurement with a strict cast, so a bad value fails the query instead of quietly becoming blank. All of that is one readable SQL definition. Trade-off: it's recalculated on every read, which costs nothing at 1,005 rows.

**Every check has its expected value fixed in advance.** The build expects 1,005 rows, 25 product codes, 29 start months, a production period of Nov 2018 to Apr 2021, a set batch count per strength and a set dissolution average, minimum and maximum. A check that only reports what it found can't tell a good load from a bad one. Trade-off: the expected values belong to this one file, so a new file needs new ones.

**The source file's SHA-256 is pinned.** The build refuses any file that isn't the verified one, before anything is built. Even one changed byte stops it, which `tests/test_build.py` checks. Trade-off: replacing the data on purpose means updating the fingerprint on purpose.

**A build only replaces the database when every check passes.** It builds in a scratch folder and swaps the result in at the end, so a failed build leaves the last good database untouched and the live app keeps serving it.

**Loads are all-or-nothing, after a dry run.** Snowflake loads through a stage with a dry run first, then a COPY INTO that loads nothing if any row fails. DuckDB parses the whole file before storing anything. A half-loaded table is worse than a failed load, because it can look complete.

**Gaps are reported, not filled in.** Missing API test results are confined to API source 3, and 10 batches have no tablet weight (8 from API source 3, 2 from source 4). The integrity tab shows these instead of imputing them, since a filled-in lab result would be an invented one.

**An API lot is identified by its source and lot number together.** Some API lot numbers appear under more than one API source, so a lot number alone would merge different materials in the genealogy.

**The SQL is reconciled against an independent pandas calculation.** `verify_profile.py` recomputes the profile with a different tool, so a mistake in either one shows up as a mismatch instead of passing quietly.

## Platform

**Built in Snowflake, live on DuckDB.** The pipeline was built in Snowflake: a stage, COPY INTO, a clean view and a Streamlit in Snowflake app, plus cloning, Time Travel, UNDROP, a Data Metric Function and a read-only role in `sql/04_exercises.sql`. When the trial ended, the same steps, expected values and app file moved to DuckDB, which runs in-process with no server or account. `local/local_session.py` stands in for Snowflake's session, so the same app file runs on both. Trade-off: the Snowflake-only exercises aren't ported.

**Streamlit for the app, with the dashboard as one self-contained page.** Streamlit in Snowflake runs inside the account, next to the data, with no web server to host. Snowflake blocks external scripts, styles and fonts there, so the dashboard is a single page with inline CSS, JavaScript and SVG charts, which also made it easy to move to DuckDB. Flask would have needed its own server, routes and templates, outside the account where the data lives.

**The app only reads.** It runs SELECT queries and nothing else, and the DuckDB stand-in opens the database read-only. A review tool shouldn't be able to change the data it reviews.

## Charts and rules

**An I-MR chart, one per product code and attribute.** Each batch has one result per attribute, so the subgroups are size one and an X-bar and R chart doesn't apply. Product codes differ in strength and batch size, so mixing them would blend different processes. Codes with fewer than 10 batches aren't charted.

**σ comes from the average moving range, not the overall standard deviation.** σ is the average moving range divided by 1.128. The overall standard deviation is inflated by shifts and trends, which widens the limits and hides the very changes the chart is there to catch.

**Two pattern rules, not all eight.** A shift (8 or more in a row on one side of the mean, a Western Electric rule) and a trend (6 or more steadily rising or falling, a Nelson rule) catch gradual drift that never crosses a 3σ limit. Every extra rule adds false alarms, so the chart uses the two that answer the main questions: has the level moved, and is it drifting?

**Limits can come from every batch or from a frozen baseline.** By default they come from every batch shown, a retrospective review. "First 20 batches, then frozen" sets them from each code's first 20 batches and judges every later batch against them, the way a plant monitors new batches. Limits that keep recalculating absorb a drift as it happens, and one bad batch can move them for everyone: in the test data, one outlier dragged the all-batch mean up far enough that 9 normal batches tripped the shift rule. Around 20 to 25 points is the usual minimum for setting individuals-chart limits, enough to estimate σ while leaving later batches to judge in the larger product codes. Trade-off: 20 batches is a short baseline, and codes with 20 or fewer batches have nothing judged against frozen limits.

**Repeated values get a warning.** When half or more of a code's results are one value, often a lab's reporting limit such as 0.050, the moving ranges collapse and the limits become unreliable. The chart warns, and the genealogy signals skip those attributes.

**A flag means worth a look, not failed.** Every batch met its specification. Control limits describe the process's own variation, and specification limits are a separate approved range, so a signal here is out of trend, not out of specification.

**Capability only with spec limits the user enters.** The public data doesn't include specification limits, and invented ones would make Cpk and Ppk meaningless, so the inputs start blank. Cpk uses the short-term σ and Ppk the overall standard deviation, both over every batch shown. A big gap between them means the process moves between batches. In the test data, a step change keeps the short-term σ small but roughly doubles the overall σ, so Ppk comes out about half of Cpk.

**Genealogy signals use the same rules and limits as the charts.** Picking a raw material lot shows every finished batch made with it, and which of those batches already had signals, with the same limits setting as Process trending. That's review by exception: the reviewer starts from the batches that need a look.

## Testing and operations

**Tests run the dashboard's real JavaScript in a browser.** The rules live in the page's JavaScript, so `tests/test_app.py` renders the real page in headless Chrome and calls the same functions the charts use. A Python copy of the rules could pass while the page itself broke. The tests load the app's functions without starting Streamlit or connecting to Snowflake.

**Keep-awake only counts a rendered dashboard as a pass.** Every 4 hours it opens the live app in a browser, wakes it if needed, and fails unless the dashboard title appears, so a green run means the app actually loaded. Each run keeps a screenshot for 7 days.

**A monthly health check rebuilds from scratch.** On the 1st of each month it reruns the build against the pinned file and commits a dated line to `ops/health-log.md`. That commit also keeps the scheduled workflows on, since GitHub switches them off in a public repo after 60 days without activity.

**Demonstration only.** The data is public and anonymized, and this is not a validated system. Nothing here should be used for GMP decisions.
