    
import os
import csv
import pandas as pd
import numpy as np

DATA_DIR = "data/raw"
OUT_DIR = "data/processed"

os.makedirs(OUT_DIR, exist_ok=True)

current_file = "Dinesafe.csv"

unified_columns = [
    "unified_est_id",
    "est_name",
    "address",
    "latitude",
    "longitude",
    "establishment_type",
    "inspection_date",
    "inspection_status",
    "severity",
    "infraction_detail",
    "violation_category",
    "enforcement_action",
    "legal_outcome",
    "amount_fined",
    "source_era",
    "source_file",
]

def read_csv_robust(path):

    rows = []
    bad_row_count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        header = [h.strip().strip('"') for h in header]
        n_cols = len(header)
        for row in reader:
            if len(row) == n_cols:
                rows.append(row)
            else:
                bad_row_count += 1

    if bad_row_count > 0:
        print(f"    note: dropped {bad_row_count} malformed row(s) in {os.path.basename(path)}")

    return pd.DataFrame(rows, columns=header)

def load_historical_file(path):
    df = read_csv_robust(path)

    out = pd.DataFrame()
    out["unified_est_id"] = df["Establishment ID"].astype(str).str.strip()
    out["est_name"] = df["Establishment Name"]
    out["address"] = df["Establishment Address"]
    out["latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    out["establishment_type"] = df["Establishment Type"]
    out["inspection_date"] = pd.to_datetime(df["Inspection Date"], errors="coerce")
    out["inspection_status"] = df["Establishment Status"]
    out["severity"] = df["Severity"]
    out["infraction_detail"] = df["Infraction Details"]
    out["violation_category"] = np.nan  #does not exist in historical set!!
    out["enforcement_action"] = df["Action"]
    out["legal_outcome"] = df["Outcome"]
    out["amount_fined"] = pd.to_numeric(df["Amount Fined"], errors="coerce")
    out["source_era"] = "historical"
    out["source_file"] = os.path.basename(path)

    return out[unified_columns]

def load_current_file(path):
    df = read_csv_robust(path)

    out = pd.DataFrame()

    out["unified_est_id"] = df["oldEstId"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    out["est_name"] = df["estName"]
    out["address"] = df["address"]
    out["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    out["establishment_type"] = np.nan          
    out["inspection_date"] = pd.to_datetime(df["inspectionDate"], errors="coerce")
    out["inspection_status"] = df["inspectionStatus"]
    out["severity"] = df["severity"]
    out["infraction_detail"] = df["deficiencyDesc"]
    out["violation_category"] = df["typeDesc"]
    out["enforcement_action"] = np.nan          
    out["legal_outcome"] = df["OutcomeDesc"]
    out["amount_fined"] = pd.to_numeric(df["amountFined"], errors="coerce")
    out["source_era"] = "current"
    out["source_file"] = os.path.basename(path)

    return out[unified_columns]


def main():
    historical_files = sorted([
        f for f in os.listdir(DATA_DIR)
        if f.endswith(".csv") and f != current_file
    ])

    if not historical_files:
        raise SystemExit(f"No historical files found in {DATA_DIR}")

    current_path = os.path.join(DATA_DIR, current_file)
    if not os.path.exists(current_path):
        raise SystemExit(f"Couldn't find '{current_file}' inside {DATA_DIR}")

    print(f"Found {len(historical_files)} historical files + 1 current file. Loading...\n")

    all_frames = []

    for fname in historical_files:
        path = os.path.join(DATA_DIR, fname)
        df = load_historical_file(path)
        all_frames.append(df)
        print(f"  loaded {fname}: {len(df):,} rows")

    df_current = load_current_file(current_path)
    all_frames.append(df_current)
    print(f"  loaded {current_file}: {len(df_current):,} rows")

    unified = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal unified rows: {len(unified):,}")

#------(checking coverage here:)------

    current_ids = set(unified.loc[unified["source_era"] == "current", "unified_est_id"].dropna())
    historical_ids = set(unified.loc[unified["source_era"] == "historical", "unified_est_id"].dropna())

    overlap = current_ids & historical_ids
    current_only = current_ids - historical_ids

    print("\n--- Join Coverage Report ---")
    print(f"Unique restaurant IDs in current era:     {len(current_ids):,}")
    print(f"Unique restaurant IDs in historical era:   {len(historical_ids):,}")
    print(f"Overlap (linked across both eras):         {len(overlap):,}")
    print(f"Current-only (no historical match found):  {len(current_only):,}")
    if len(current_ids) > 0:
        pct = 100 * len(overlap) / len(current_ids)
        print(f"-> {pct:.1f}% of current restaurants have at least one linked historical record")
    print("-----------------------------\n")

    csv_out = os.path.join(OUT_DIR, "dinesafe_unified.csv")
    unified.to_csv(csv_out, index=False)
    print(f"Saved CSV:     {csv_out}")

    try:
        parquet_out = os.path.join(OUT_DIR, "dinesafe_unified.parquet")
        unified.to_parquet(parquet_out, index=False)
        print(f"Saved Parquet: {parquet_out}")
    except ImportError:
        print("paraquet save isnt enabled yet!!")


    print("\nDone.")


if __name__ == "__main__":
    main()
