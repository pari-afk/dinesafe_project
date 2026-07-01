import csv
import os
import json
import pandas as pd

DATA_DIR = "data/raw"
OUT_DIR = "data/processed"

os.makedirs(OUT_DIR, exist_ok=True)

files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".csv")])

if not files:
    raise SystemExit(f"No csv files found. Recheck the path.")

results = []

for fname in files:
    path = os.path.join(DATA_DIR, fname)
    entry = {"file": fname}

    try:
        with open(path, "r", encoding="utf-8", errors="strict") as f:
            reader = csv.reader(f)
            header = next(reader)
            header_clean = [h.strip().strip('"') for h in header]
            n_cols = len(header_clean)

            good_rows = 0
            bad_rows = 0
            bad_rows_examples = []
            for i, row in enumerate(reader):
                if len(row) == n_cols:
                    good_rows += 1
                else:
                    bad_rows += 1
                    if len(bad_rows_examples) < 3:
                        bad_rows_examples.append({"line_approx": i + 2, "n_fields": len(row)})

        entry["header"] = header_clean
        entry["n_cols"] = n_cols
        entry["csv_module_good_rows"] = good_rows
        entry["csv_module_bad_rows_examples"] = bad_rows_examples
        entry["encoding_errors"] = False

    except UnicodeDecodeError as e:
         entry["encoding_errors"] = True
         entry["encoding_error_detail"] = str(e)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader)
            header_clean = [h.strip().strip('"') for h in header]
            n_cols = len(header_clean)
            good_rows = sum(1 for row in reader if len(row) == n_cols)
            entry["header"] = header_clean
            entry["n_cols"] = n_cols
            entry["csv_module_good_rows"] = good_rows
            entry["csv_module_bad_rows"] = 0

        
            try:     
             df_pandas = pd.read_csv(path)
             entry["pandas_c_engine_status"] = "success"
             entry["pandas_c_engine_rows"] = len(df_pandas)
            except Exception as e:
             entry["pandas_c_engine_status"] = "FAILED"
             entry["pandas_c_engine_error"] = str(e)[:300]

    results.append(entry)
    print(f"Audited {fname}: cols={entry.get('n_cols')}, "
          f"rows={entry.get('csv_module_good_rows')}, "
          f"bad_rows={entry.get('csv_module_bad_rows', 0)}, "
          f"pandas={entry.get('pandas_c_engine_status')}")

json_path = os.path.join(OUT_DIR, "audit_results.json")
with open(json_path, "w") as f:
    json.dump(results, f, indent=2)

all_schemas = {}
for r in results:
    key = tuple(r["header"])
    all_schemas.setdefault(key, []).append(r["file"])

SCHEMA_DICTIONARY = {
    "Rec #": "_id",
    "Establishment ID": "oldEstId",
    "Inspection ID": "unique_id",
    "Establishment Name": "estName",
    "Establishment Type": "typeDesc_category",   
    "Establishment Address": "address",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Establishment Status": "inspectionStatus",
    "Min. Inspections Per Year": None,            # not present in current schema
    "Infraction Details": "deficiencyDesc",
    "Inspection Date": "inspectionDate",
    "Severity": "severity",
    "Action": "OutcomeDesc",
    "Outcome": "OutcomeDesc",
    "Amount Fined": "amountFined",
}

md_path = os.path.join(OUT_DIR, "audit_report.md")
with open(md_path, "w") as f:
    f.write("# DineSafe Data Audit Report (Step 1)\n\n")

    f.write("## File-by-file summary\n\n")
    f.write("| File | Columns | Rows (valid) | Malformed rows | pandas read_csv() |\n")
    f.write("|------|---------|--------------|-----------------|--------------------|\n")
    for r in results:
        pandas_note = r["pandas_c_engine_status"]
        if pandas_note == "FAILED":
            pandas_note = "**FAILED**"
        f.write(f"| {r['file']} | {r['n_cols']} | {r['csv_module_good_rows']} | "
                f"{r.get('csv_module_bad_rows', 0)} | {pandas_note} |\n")

    f.write("\n## Distinct schemas found\n\n")
    f.write(f"There are **{len(all_schemas)} distinct column header layouts** across all files.\n\n")
    for i, (schema, files_using_it) in enumerate(all_schemas.items(), 1):
        f.write(f"### Schema {i} (used by {len(files_using_it)} file(s): {', '.join(files_using_it)})\n\n")
        f.write("Columns: " + ", ".join(schema) + "\n\n")

    f.write("## Schema dictionary (old field name -> new field name)\n\n")
    f.write("| Historical field (2001-2022 files) | Current field (Dinesafe.csv) | Notes |\n")
    f.write("|-------------------------------------|-------------------------------|-------|\n")
    for old_name, new_name in SCHEMA_DICTIONARY.items():
        if new_name is None:
            f.write(f"| {old_name} | *(no equivalent)* | Dropped/unused in current schema |\n")
        else:
            f.write(f"| {old_name} | {new_name} | |\n")
    f.write("\n*Note: `Establishment Type` has no direct equivalent in the current schema - "
            "the current file encodes infraction category info differently via `typeDesc`. "
            "This needs manual review before being used in the pipeline.*\n")
    f.write("\n*Note: both `Action` and `Outcome` in the historical schema appear to map "
            "loosely onto `OutcomeDesc` in the current schema - needs verification, "
            "they may not be a clean 1:1 mapping.*\n")

    f.write("\n## Files where pandas.read_csv() failed by default\n\n")
    failed = [r for r in results if r["pandas_c_engine_status"] == "FAILED"]
    if failed:
        for r in failed:
            f.write(f"- **{r['file']}**: `{r['pandas_c_engine_error']}`\n")
        f.write("\nThese files contain a quote-escaping issue (an unescaped or unterminated "
                "quote character inside a free-text field) that breaks pandas' default C "
                "parser. They parsed fine using Python's built-in `csv` module instead, "
                "so the ingestion pipeline should read these files using `csv` directly, "
                "or `pandas.read_csv(..., engine='python')`, rather than the pandas default.\n")
    else:
        f.write("None - all files loaded successfully with pandas defaults.\n")

    f.write("\n## Files with malformed rows (field count mismatch vs header)\n\n")
    malformed = [r for r in results if r.get("csv_module_bad_rows", 0) > 0]
    if malformed:
        for r in malformed:
            f.write(f"- **{r['file']}**: {r['csv_module_bad_rows']} malformed row(s). "
                     f"Examples: {r['csv_module_bad_row_examples']}\n")
    else:
        f.write("None found via the csv module.\n")

    f.write("\n## Total row count across all files (valid rows only)\n\n")
    total_rows = sum(r["csv_module_good_rows"] for r in results)
    f.write(f"**{total_rows:,}** total inspection records across {len(results)} files.\n")

print("\nDone.")
