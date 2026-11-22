# Glossary

The pharma, SPC and Snowflake terms used in Batch Monitor, in plain language.

## Pharma and quality

**ALCOA+.** Data integrity principles from pharma guidance: records should be Attributable, Legible, Contemporaneous, Original and Accurate, plus Complete, Consistent, Enduring and Available. This project borrows a few of the ideas (the original file kept unchanged, a pinned fingerprint, a load log with time and source) without claiming compliance.

**API (active pharmaceutical ingredient).** The drug substance in a tablet. Each batch records which API source and lot it used.

**Batch and lot.** Here a batch is one production run of finished tablets, and a lot is a quantity of raw material received and tested as one unit. Genealogy links the two.

**CPV (continued process verification).** Ongoing monitoring of a validated process with trending and statistics. It's the third stage of process validation in FDA guidance.

**CQA and CPP.** A critical quality attribute is a product property that has to stay within limits, such as dissolution or impurities. A critical process parameter is a process setting that affects one, such as compression force. This app charts CQAs.

**Direct compression and film coating.** The tablets here are made by compressing the powder blend directly, without granulating it first, and then coated with a thin film.

**Dissolution.** A lab test of how much drug a tablet releases in a set time, in percent. The data has the average and the minimum across the tablets tested.

**Excipient.** An inactive ingredient. Here: lactose, silicified microcrystalline cellulose and starch.

**Genealogy.** Tracing which raw material lots went into which finished batches, and back.

**GMP (Good Manufacturing Practice).** The regulations that govern how medicines are made and documented. Systems used for GMP decisions have to be validated, which this demonstration is not.

**OOS and OOT.** Out of specification: a result outside its approved limits, which triggers a formal investigation. Out of trend: a result within specification but unusual for the process's history. This app's signals are OOT.

**Reporting limit.** The lowest value a lab method reports. Results below it are recorded at the limit, which piles up repeated values.

**Residual solvent.** Solvent left in the product from manufacturing, measured as a quality attribute.

**Specification limits (LSL and USL).** The approved acceptance range for a result, lower and upper. The public data doesn't include them.

## Statistical process control

**Control limits.** The range a stable process normally stays within, set at the mean ± 3σ from the process's own results. They are not specification limits.

**Cpk and Ppk.** Capability indices: how far the mean sits from the nearest spec limit, in units of 3σ. Cpk uses the short-term σ from moving ranges, Ppk the overall standard deviation. 1.33 or more is a common target.

**Frozen limits (Phase I and Phase II).** Phase I sets control limits from a baseline of batches. Phase II judges new batches against those fixed limits. "First 20 batches, then frozen" is this setup.

**I-MR chart.** Individuals and moving range chart. It plots each result in production order, plus the change from the previous result, for data with one value per batch.

**Moving range.** The absolute difference between two consecutive results.

**Western Electric and Nelson rules.** Sets of pattern rules for control charts. This app uses one from each: a shift of 8 in a row on one side of the mean, and a trend of 6 steadily rising or falling.

## Data and Snowflake

**SHA-256 fingerprint.** A 64-character code computed from a file's bytes. Any change to the file, even one byte, gives a different code.

**Stage and COPY INTO.** A stage is a storage location Snowflake loads files from. COPY INTO loads staged files into a table.

**Time Travel, zero-copy clone and UNDROP.** Time Travel queries or restores data as it was at an earlier point. A zero-copy clone is an instant copy that shares storage until either side changes. UNDROP restores a dropped object.

**Data Metric Function.** A function Snowflake can run on a schedule to measure data quality on a table.
