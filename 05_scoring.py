import os
import pandas as pd
import numpy as np

IN_DIR = "data/processed"
OUT_DIR = "data/scored"
os.makedirs(OUT_DIR, exist_ok=True)

in_parquet = os.path.join(IN_DIR, "dinesafe_clean.parquet")
in_csv = os.path.join(IN_DIR, "dinesafe_clean.csv")

out_csv = os.path.join(OUT_DIR, "restaurant_scores.csv")
out_parquet = os.path.join(OUT_DIR, "restaurant_scores.parquet")
methodology_path = os.path.join(OUT_DIR, "scoring_methodology.md")

severity_weights = {
    "C - Crucial": 5,
    "S - Significant": 2,
    "M - Minor": 1,
    "NO_SEVERITY": 0,
}
half_life_years = 2.5  # a violation's weight halves every 2.5 years
shrinkage_k = 10


def load_clean():
    if os.path.exists(in_parquet):
        return pd.read_parquet(in_parquet)
    elif os.path.exists(in_csv):
        return pd.read_csv(in_csv, parse_dates=["inspection_date"])
    else:
        raise SystemExit(f"cant find dinesafe_clean.parquet or .csv in {IN_DIR}")


def assign_stars(penalty, cutoffs):

    if penalty <= cutoffs[0]:
        return 5
    elif penalty <= cutoffs[1]:
        return 4
    elif penalty <= cutoffs[2]:
        return 3
    elif penalty <= cutoffs[3]:
        return 2
    else:
        return 1

def main():
    df = load_clean()
    df_valid = df[df["has_valid_id"]].copy()
    print(f"Loaded {len(df_valid):,} valid rows.\n")

    current_ids = set(
        df_valid.loc[df_valid["source_era"] == "current", "unified_est_id"]
    )
    print(f"Currently-operating restaurants: {len(current_ids):,}")

    scoped = df_valid[df_valid["unified_est_id"].isin(current_ids)].copy()
    print(f"Total inspection rows across their full history: {len(scoped):,}\n")

    scoped["severity_weight"] = scoped["severity"].map(severity_weights)

    now = scoped["inspection_date"].max()
    print(f"Anchor date for recency decay: {now.date()}\n")

    scoped["years_ago"] = (now - scoped["inspection_date"]).dt.days / 365.25
    scoped["decay_weight"] = 0.5 ** (scoped["years_ago"] / half_life_years)
    scoped["penalty"] = scoped["severity_weight"] * scoped["decay_weight"]

    agg = (
        scoped.groupby("unified_est_id")
        .agg(
            total_decayed_penalty=("penalty", "sum"),
            n_inspections=("unified_est_id", "size"),
            n_violations=("severity_weight", lambda x: (x > 0).sum()),
            est_name=("est_name", "last"),  
            address=("address", "last"),    
        )
        .reset_index()
    )
    agg["avg_penalty_per_inspection"] = (
        agg["total_decayed_penalty"] / agg["n_inspections"]
    )

    global_mean_penalty = agg["total_decayed_penalty"].sum() / agg["n_inspections"].sum()
    print(f"Citywide average penalty per inspection: {global_mean_penalty: .4f}\n")

    agg["shrunk_avg_penalty"] = (
        (agg["n_inspections"] * agg["avg_penalty_per_inspection"] + shrinkage_k * global_mean_penalty)
        / (agg["n_inspections"] + shrinkage_k)
    )

    unique_visits = scoped[["unified_est_id", "inspection_date"]].drop_duplicates()
    population_median_gap = (
        unique_visits.sort_values("inspection_date")
        .groupby("unified_est_id")["inspection_date"]
        .apply(lambda dates: dates.diff().dt.days.dropna())
        .median()
    )

    def compute_overdue_stats(dates):
        dates = dates.sort_values()
        gaps = dates.diff().dt.days.dropna()
        typical_gap = gaps.median() if len(gaps) >= 3 else population_median_gap
        days_since_last = (scoped["inspection_date"].max() - dates.max()).days
        return pd.Series({
            "days_since_last": days_since_last,
            "typical_gap": typical_gap,
            "overdue_ratio": days_since_last / typical_gap,
        })

    overdue_stats = (
        unique_visits.groupby("unified_est_id")["inspection_date"]
        .apply(compute_overdue_stats)
        .unstack()
        .reset_index()
    )

    overdue_cutoff = overdue_stats["overdue_ratio"].quantile(0.95)
    overdue_stats["is_overdue"] = overdue_stats["overdue_ratio"] >= overdue_cutoff

    print(f"\nOverdue-for-inspection flag: top 5% cutoff = {overdue_cutoff:.2f}x, "
          f"flagging {overdue_stats['is_overdue'].sum():,} of {len(overdue_stats):,} restaurants")

    agg = agg.merge(
        overdue_stats[["unified_est_id", "days_since_last", "typical_gap", "overdue_ratio", "is_overdue"]],
        on="unified_est_id",
    )
    
    print("=== shrunk_avg_penalty distribution ===")
    print(agg["shrunk_avg_penalty"].describe())
    print()

    cutoffs = agg["shrunk_avg_penalty"].quantile([0.2, 0.4, 0.6, 0.8]).values
    print("Quintile cutoffs (5-star/4/3/2 boundary, 1-star is anything above):")
    print(cutoffs)
    print()

    agg["stars"] = agg["shrunk_avg_penalty"].apply(
        lambda x: assign_stars(x, cutoffs)
    )

    print("=== Star distribution ===")
    print(agg["stars"].value_counts().sort_index())
    print()

    min_inspections_5star = agg[agg["stars"] ==5]["n_inspections"].min()
    print(f"Minimum inspections among 5-star restaurants: {min_inspections_5star}\n")

    agg = agg.sort_values("shrunk_avg_penalty")
    agg.to_csv(out_csv, index=False)
    print(f"Saved CSV:     {out_csv}")

    try:
        agg.to_parquet(out_parquet, index=False)
        print(f"Saved Parquet: {out_parquet}")
    except ImportError:
        print("Skipped Parquet save - install pyarrow to enable it.")

    star_counts = agg["stars"].value_counts().sort_index()
    
    print("\nDone.")


if __name__ == "__main__":
    main()
        

        
        

    
    
