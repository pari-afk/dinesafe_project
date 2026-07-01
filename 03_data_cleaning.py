import os
import pandas as pd
import numpy as np

IN_DIR = "data/processed"
OUT_DIR = "data/processed"
os.makedirs(OUT_DIR, exist_ok=True)

in_parquet = os.path.join(IN_DIR, "dinesafe_unified.parquet")
in_csv = os.path.join(IN_DIR, "dinesafe_unified.csv")
out_parquet = os.path.join(OUT_DIR, "dinesafe_clean.parquet")
out_csv = os.path.join(OUT_DIR, "dinesafe_clean.csv")
report_path = os.path.join(OUT_DIR, "data_quality_notes.md")

null_severity_values = ["", "None", "NA - Not Applicable", "NA"]

def load_unified():
    if os.path.exists(in_parquet):
        return pd.read_parquet(in_parquet)
    elif os.path.exists(in_csv):
        return pd.read_csv(in_csv)
    else:
        raise SystemExit(f"cant find dinesafe_unified.parquet or .csv in {IN_DIR}")

def main():
    df = load_unified()
    n_start = len(df)
    print(f"Loaded {n_start:,} rows from previous output.\n")

    df = df.replace(r"^\s*$", np.nan, regex=True)

    for col in ["unified_est_id", "est_name", "address"]:
        n_literal_none = (df[col] == "None").sum()
        if n_literal_none > 0:
            print(f" found {n_literal_none} rows where {col} == literal string 'None'")
            df.loc[df[col] == "None", col] = np.nan

    df["severity"] = df["severity"].replace(null_severity_values, "NO_SEVERITY")
    df["severity"] = df["severity"].fillna("NO_SEVERITY")
    severity_counts = df["severity"].value_counts(dropna=False)
    print("\nSeverity breakdown after standardization:")
    print(severity_counts)
    
    missing_id_mask = df["unified_est_id"].isna()
    n_missing_id = missing_id_mask.sum()
    print(f"\nRows with missing unified_est_id: {n_missing_id:,}")
    df["has_valid_id"] = ~missing_id_mask

    key_fields = ["inspection_date", "inspection_status", "est_name", "address"]
    null_report = df[key_fields].isna().sum()
    print("\nNull counts in other key fields:")
    print(null_report)

    dedup_cols = [c for c in df.columns if c != "source_file"]
    n_exact_dupes = df.duplicated(subset=dedup_cols).sum()
    df = df.drop_duplicates(subset=dedup_cols, keep="first")
    print(f"\nDropped {n_exact_dupes:,} exact duplicate rows.")
    
    n_dupe_inspection = df.duplicated(
        subset=["unified_est_id", "inspection_date", "infraction_detail"]
    ).sum()
    df = df.drop_duplicates(
        subset=["unified_est_id", "inspection_date", "infraction_detail"],
        keep="first",
    )
    print(f"Dropped {n_dupe_inspection:,} duplicate same-restaurant/date/infraction rows.")

    valid_id_df = df[df["has_valid_id"]]
    name_variation = valid_id_df.groupby("unified_est_id")["est_name"].nunique()
    addr_variation = valid_id_df.groupby("unified_est_id")["address"].nunique()
    n_multi_name = (name_variation > 1).sum()
    n_multi_addr = (addr_variation > 1).sum()
    print(f"\nRestaurants with >1 distinct name on record: {n_multi_name:,} of {len(name_variation):,}")
    print(f"Restaurants with >1 distinct address on record: {n_multi_addr:,} of {len(addr_variation):,}")
    
    n_final = len(df)
    print(f"\nFinal row count: {n_final:,} (started at {n_start:,})")

    df.to_csv(out_csv, index=False)
    print(f"Saved CSV:     {out_csv}")

    try:
        df.to_parquet(out_parquet, index=False)
        print(f"Saved Parquet: {out_parquet}")
    except ImportError:
        print("skipped parquet")

    print("\nDone.")

if __name__ == "__main__":
    main()    
