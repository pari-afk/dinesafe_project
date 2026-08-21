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

RESTAURANT_TYPES = [
    "Restaurant",
    "Food Take Out",
    "Food Court Vendor",
    "Cocktail Bar / Beverage Room",
    "Bakery",
    "Bake Shop",
    "Ice Cream / Yogurt Vendors",
    "Hot Dog Cart",
    "Refreshment Stand (Stationary)",
    "Food Cart",
    "Mobile Food Preparation Premises",
    "Restaurant (confirmed, no prior history)",
]

CONFIRMED_NO_HISTORY_PATH = "/Users/paribhatnagar/Desktop/dinesafe-project/data/manual/confirmed_no_history_restaurants.csv"

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

    #backfill 1: borrowing est type from restaurants historical record
    type_lookup = (
        df[(df["source_era"] == "historical") & df["establishment_type"].notna()]
        .drop_duplicates(subset="unified_est_id")
        .set_index("unified_est_id")["establishment_type"]
    )

    n_current_total = (df["source_era"] == "current").sum()
    missing_mask = (df["source_era"] == "current") & df["establishment_type"].isna()
    df.loc[missing_mask, "establishment_type"] = df.loc[missing_mask, "unified_est_id"].map(type_lookup)

    n_after_historical_backfill = ((df["source_era"] == "current") & df["establishment_type"].isna()).sum()
    print(
        f"\nHistorical backfill: {n_current_total - n_after_historical_backfill: ,} of "
        f"{n_current_total: ,} current-era rows matched to a historical record."
    )

    #backfill 2: for current-era rows with no historical records at all
    #check against the manually & automatically confirmed restaurant list
    #built w Toronto open Data + manual research (in README).
    confirmed = pd.read_csv(CONFIRMED_NO_HISTORY_PATH)
    confirmed["unified_est_id"] = (
        confirmed["unified_est_id"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    )
    confirmed_ids = set(confirmed["unified_est_id"].dropna())

    still_missing_mask = (df["source_era"] == "current") & df["establishment_type"].isna()
    confirmed_match_mask = still_missing_mask & df["unified_est_id"].isin(confirmed_ids)
    df.loc[confirmed_match_mask, "establishment_type"] = "Restaurant (confirmed, no prior history)"

    n_confirmed_matched = confirmed_match_mask.sum()
    n_still_unresolved = ((df["source_era"] == "current") & df["establishment_type"].isna()).sum()
    print(
        f"No history confirmed. List backfill: {n_confirmed_matched: ,} additional rows "
        f"matched. {n_still_unresolved: ,} current-era rows remain unclassified and "
        f"will be excluded (no historical record and not in the confirmed list)."
    )
    
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

    n_before_type_filter = len(df)
    n_unique_before = df["unified_est_id"].nunique()

    df["establishment_type"] = df["establishment_type"].str.strip()
    df = df[df["establishment_type"].isin(RESTAURANT_TYPES)]

    n_after_type_filter = len(df)
    n_unique_after = df["unified_est_id"].nunique()

    print(
        f"\nFiltered to restaurant-type establishments only: "
        f"kept {n_after_type_filter: ,} of {n_before_type_filter: ,} inspection rows "
        f"({n_unique_after: ,} of {n_unique_before: ,} unique establishments)."
    )

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
