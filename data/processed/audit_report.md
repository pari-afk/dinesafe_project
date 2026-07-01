# DineSafe Data Audit Report (Step 1)

## File-by-file summary

| File | Columns | Rows (valid) | Malformed rows | pandas read_csv() |
|------|---------|--------------|-----------------|--------------------|
| Dinesafe.csv | 18 | 102755 | 0 | success |
| dinesafe_hist_2001.csv | 16 | 6066 | 0 | success |
| dinesafe_hist_2002.csv | 16 | 6352 | 0 | success |
| dinesafe_hist_2003.csv | 16 | 7160 | 0 | success |
| dinesafe_hist_2004.csv | 16 | 7181 | 0 | success |
| dinesafe_hist_2005.csv | 16 | 8642 | 0 | success |
| dinesafe_hist_2006.csv | 16 | 9096 | 0 | success |
| dinesafe_hist_2007.csv | 16 | 10130 | 0 | success |
| dinesafe_hist_2008.csv | 16 | 11666 | 0 | success |
| dinesafe_hist_2009.csv | 16 | 11393 | 0 | success |
| dinesafe_hist_2010.csv | 16 | 14920 | 0 | success |
| dinesafe_hist_2011.csv | 16 | 16624 | 0 | success |
| dinesafe_hist_2012.csv | 16 | 17188 | 0 | success |
| dinesafe_hist_2013.csv | 16 | 20392 | 0 | success |
| dinesafe_hist_2014.csv | 16 | 23160 | 0 | success |
| dinesafe_hist_2015.csv | 16 | 21750 | 0 | success |
| dinesafe_hist_2016.csv | 16 | 24300 | 0 | success |
| dinesafe_hist_2017.csv | 16 | 26989 | 0 | success |
| dinesafe_hist_2018.csv | 16 | 29026 | 0 | success |
| dinesafe_hist_2019.csv | 16 | 34493 | 0 | success |
| dinesafe_hist_2020.csv | 16 | 11714 | 0 | **FAILED** |
| dinesafe_hist_2021.csv | 16 | 9070 | 0 | **FAILED** |
| dinesafe_hist_2022.csv | 16 | 30478 | 0 | **FAILED** |

## Distinct schemas found

There are **2 distinct column header layouts** across all files.

### Schema 1 (used by 1 file(s): Dinesafe.csv)

Columns: _id, unique_id, estId, oldEstId, estName, address, inspectionStatus, phone, inspectionDate, observation, typeDesc, deficiencyDesc, severity, OutcomeDate, OutcomeDesc, amountFined, latitude, longitude

### Schema 2 (used by 22 file(s): dinesafe_hist_2001.csv, dinesafe_hist_2002.csv, dinesafe_hist_2003.csv, dinesafe_hist_2004.csv, dinesafe_hist_2005.csv, dinesafe_hist_2006.csv, dinesafe_hist_2007.csv, dinesafe_hist_2008.csv, dinesafe_hist_2009.csv, dinesafe_hist_2010.csv, dinesafe_hist_2011.csv, dinesafe_hist_2012.csv, dinesafe_hist_2013.csv, dinesafe_hist_2014.csv, dinesafe_hist_2015.csv, dinesafe_hist_2016.csv, dinesafe_hist_2017.csv, dinesafe_hist_2018.csv, dinesafe_hist_2019.csv, dinesafe_hist_2020.csv, dinesafe_hist_2021.csv, dinesafe_hist_2022.csv)

Columns: Rec #, Establishment ID, Inspection ID, Establishment Name, Establishment Type, Establishment Address, Latitude, Longitude, Establishment Status, Min. Inspections Per Year, Infraction Details, Inspection Date, Severity, Action, Outcome, Amount Fined

## Schema dictionary (old field name -> new field name)

| Historical field (2001-2022 files) | Current field (Dinesafe.csv) | Notes |
|-------------------------------------|-------------------------------|-------|
| Rec # | _id | |
| Establishment ID | oldEstId | |
| Inspection ID | unique_id | |
| Establishment Name | estName | |
| Establishment Type | typeDesc_category | |
| Establishment Address | address | |
| Latitude | latitude | |
| Longitude | longitude | |
| Establishment Status | inspectionStatus | |
| Min. Inspections Per Year | *(no equivalent)* | Dropped/unused in current schema |
| Infraction Details | deficiencyDesc | |
| Inspection Date | inspectionDate | |
| Severity | severity | |
| Action | OutcomeDesc | |
| Outcome | OutcomeDesc | |
| Amount Fined | amountFined | |

*Note: `Establishment Type` has no direct equivalent in the current schema - the current file encodes infraction category info differently via `typeDesc`. This needs manual review before being used in the pipeline.*

*Note: both `Action` and `Outcome` in the historical schema appear to map loosely onto `OutcomeDesc` in the current schema - needs verification, they may not be a clean 1:1 mapping.*

## Files where pandas.read_csv() failed by default

- **dinesafe_hist_2020.csv**: `Error tokenizing data. C error: EOF inside string starting at row 11714`
- **dinesafe_hist_2021.csv**: `Error tokenizing data. C error: EOF inside string starting at row 9070`
- **dinesafe_hist_2022.csv**: `Error tokenizing data. C error: EOF inside string starting at row 30478`

These files contain a quote-escaping issue (an unescaped or unterminated quote character inside a free-text field) that breaks pandas' default C parser. They parsed fine using Python's built-in `csv` module instead, so the ingestion pipeline should read these files using `csv` directly, or `pandas.read_csv(..., engine='python')`, rather than the pandas default.

## Files with malformed rows (field count mismatch vs header)

None found via the csv module.

## Total row count across all files (valid rows only)

**460,545** total inspection records across 23 files.
