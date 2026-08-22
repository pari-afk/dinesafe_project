import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

IN_DIR = "data/processed"
SCORES_DIR = "data/scored"
OUT_DIR = "data/validation"
os.makedirs(OUT_DIR, exist_ok=True)

in_parquet = os.path.join(IN_DIR, "dinesafe_clean.parquet")
in_csv = os.path.join(IN_DIR, "dinesafe_clean.csv")

scores_parquet = os.path.join(SCORES_DIR, "restaurant_scores.parquet")
scores_csv = os.path.join(SCORES_DIR, "restaurant_scores.csv")

out_scores_csv = os.path.join(OUT_DIR, "restaurant_scores_v2.csv")
out_scores_parquet = os.path.join(OUT_DIR, "restaurant_scores_v2.parquet")
validation_report_path = os.path.join(OUT_DIR, "validation_report.md")

severity_weights = {
    "C - Crucial": 5,
    "S - Significant": 2,
    "M - Minor": 1,
    "NO_SEVERITY": 0,
}
half_life_years = 2.5

spot_check_names = [
    "SWISS CHALET", "PIZZA PIZZA", "THE KEG", "TIM HORTONS",
    "KINTON RAMEN", "JACK ASTOR", "EARLS",
]


def load_clean():
    if os.path.exists(in_parquet):
        return pd.read_parquet(in_parquet)
    elif os.path.exists(in_csv):
        return pd.read_csv(in_csv, parse_dates=["inspection_date"])
    else:
        raise SystemExit(f"cant find dinesafe_clean.parquet or .csv in {IN_DIR}")


def load_scores():
    if os.path.exists(scores_parquet):
        return pd.read_parquet(scores_parquet)
    elif os.path.exists(scores_csv):
        return pd.read_csv(scores_csv)
    else:
        raise SystemExit(f"Couldn't find restaurant_scores from 05_scoring.py -- run that first.")


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
    scoped = df_valid[df_valid["unified_est_id"].isin(current_ids)].copy()
    print(f"Currently-operating restaurants: {len(current_ids):,}")
    print(f"Total inspection rows across their full history: {len(scoped):,}\n")

    scoped["severity_weight"] = scoped["severity"].map(severity_weights)
    now = scoped["inspection_date"].max()
    scoped["years_ago"] = (now - scoped["inspection_date"]).dt.days / 365.25
    scoped["decay_weight"] = 0.5 ** (scoped["years_ago"] / half_life_years)
    scoped["penalty"] = scoped["severity_weight"] * scoped["decay_weight"]

    agg = load_scores()
    print(f"Loaded {len(agg):,} scored restaurants from 05_scoring.py output.\n")

    agg["adjusted_penalty"] = agg["shrunk_avg_penalty"]

    print("=== n_inspections by star rating (should generally increase with stars) ===")
    print(agg.groupby("stars")["n_inspections"].agg(["mean", "min", "median", "max"]))
    print()

    merged = scoped.merge(agg[["unified_est_id", "stars"]], on="unified_est_id")
    severity_by_star = merged.groupby("stars")["severity_weight"].mean()
    print("=== Validation 1: avg raw severity weight by star rating ===")
    print(severity_by_star)
    print()

    fig, ax = plt.subplots(figsize=(7, 5))
    severity_by_star.sort_index().plot(kind="bar", ax=ax, color="steelblue")
    ax.set_xlabel("Star rating")
    ax.set_ylabel("Average raw severity weight")
    ax.set_title("Validation: severity exposure drops as star rating rises")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "validation_severity_by_star.png"))
    plt.close(fig)
    print("Saved chart: validation_severity_by_star.png\n")

    scoped["is_closed"] = (
        (scoped["inspection_status"] == "Closed")
        | scoped["legal_outcome"].str.contains("close", case=False, na=False)
        | (scoped["enforcement_action"] == "Closure Order")
    )
    ever_closed = scoped.groupby("unified_est_id")["is_closed"].any()
    agg = agg.merge(ever_closed.rename("ever_closed"), on="unified_est_id")
    closed_by_star = agg.groupby("stars")["ever_closed"].mean() * 100
    print("Validation 2: % of restaurants ever marked 'Closed', by star rating")
    print(closed_by_star)
    print()

    fig, ax = plt.subplots(figsize=(7, 5))
    closed_by_star.sort_index().plot(kind="bar", ax=ax, color="firebrick")
    ax.set_xlabel("Star rating")
    ax.set_ylabel("% of restaurants ever marked 'Closed'")
    ax.set_title("Validation: closure rate drops as star rating rises")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "validation_closed_rate_by_star.png"))
    plt.close(fig)
    print("Saved chart: validation_closed_rate_by_star.png\n")

    agg["unadjusted_penalty"] = agg["avg_penalty_per_inspection"]
    cutoffs_unadj = agg["unadjusted_penalty"].quantile([0.2, 0.4, 0.6, 0.8]).values
    agg["stars_unadjusted"] = agg["unadjusted_penalty"].apply(
        lambda x: assign_stars(x, cutoffs_unadj)
    )

    insp_before = agg.groupby("stars_unadjusted")["n_inspections"].mean()
    insp_after = agg.groupby("stars")["n_inspections"].mean()

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(1, 6)
    width = 0.35
    ax.bar(x - width / 2, [insp_before.get(s, 0) for s in x], width, label="Before fix", color="lightgray")
    ax.bar(x + width / 2, [insp_after.get(s, 0) for s in x], width, label="After shrinkage fix", color="seagreen")
    ax.set_xlabel("Star rating")
    ax.set_ylabel("Average inspection count")
    ax.set_title("Why the shrinkage fix mattered: avg inspections per star tier")
    ax.set_xticks(x)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "validation_shrinkage_fix.png"))
    plt.close(fig)
    print("Saved chart: validation_shrinkage_fix.png\n")

    print("=== Spot-check: recognizable restaurant names and their scores ===")
    spot_check_rows = []
    for name in spot_check_names:
        matches = agg[agg["est_name"].str.contains(name, case=False, na=False)]
        for _, row in matches.iterrows():
            spot_check_rows.append(row)

    if spot_check_rows:
        spot_df = pd.DataFrame(spot_check_rows)[
            ["est_name", "address", "n_inspections", "stars"]
        ].sort_values("est_name")
        print(spot_df.to_string(index=False))
    else:
        print("No matches found for the spot-check names - dataset may not contain them.")
    print()

    agg_out = agg.drop(columns=["unadjusted_penalty", "stars_unadjusted", "adjusted_penalty"], errors="ignore")
    agg_out = agg_out.sort_values("shrunk_avg_penalty")
    agg_out.to_csv(out_scores_csv, index=False)
    print(f"Saved CSV:     {out_scores_csv}")
    try:
        agg_out.to_parquet(out_scores_parquet, index=False)
        print(f"Saved Parquet: {out_scores_parquet}")
    except ImportError:
        print("install pyarrow to enable")

    print("\nDone.")


if __name__ == "__main__":
    main()
