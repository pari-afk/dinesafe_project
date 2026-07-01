import os
import pandas as pd
import matplotlib.pyplot as plt

IN_DIR = "data/processed"
OUT_DIR = "data/eda"
os.makedirs(OUT_DIR, exist_ok=True)

in_parquet = os.path.join(IN_DIR, "dinesafe_clean.parquet")
in_csv = os.path.join(IN_DIR, "dinesafe_clean.csv")
findings_path = os.path.join(OUT_DIR, "eda_findings.md")


def load_clean():
    if os.path.exists(in_parquet):
        return pd.read_parquet(in_parquet)
    elif os.path.exists(in_csv):
        return pd.read_csv(in_csv, parse_dates=["inspection_date"])
    else:
        raise SystemExit(f"cant find dinesafe_clean.parquet or .csv in {IN_DIR}")


def main():
    df = load_clean()
    print(f"Loaded {len(df):,} rows.\n")

    df_valid = df[df["has_valid_id"]].copy()
    findings = []

# ---- violations per restaurant!!

    violations = df_valid[df_valid["severity"] != "NO_SEVERITY"]
    viol_per_restaurant = violations.groupby("unified_est_id").size()

    print("=== Violations per restaurant ===")
    print(viol_per_restaurant.describe())
    print()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(viol_per_restaurant.clip(upper=100), bins=50)
    ax.set_xlabel("Violations per restaurant (clipped at 100 for readability)")
    ax.set_ylabel("Number of restaurants")
    ax.set_title("Distribution of total violations per restaurant")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "violations_per_restaurant.png"))
    plt.close(fig)
    print(f"Saved chart: violations_per_restaurant.png\n")


# ---- severity mix over a period of time!!
    df_valid["year"] = df_valid["inspection_date"].dt.year
    severity_by_year = df_valid.groupby(["year", "severity"]).size().unstack(fill_value=0)
    severity_pct_by_year = severity_by_year.div(severity_by_year.sum(axis=1), axis=0) * 100

    print("=== Severity mix by year (%) ===")
    print(severity_pct_by_year.round(1))
    print()

    fig, ax = plt.subplots(figsize=(10, 6))
    severity_pct_by_year.plot(ax=ax)
    ax.set_xlabel("Year")
    ax.set_ylabel("% of inspections")
    ax.set_title("Severity mix over time")
    ax.legend(title="Severity")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "severity_over_time.png"))
    plt.close(fig)
    print(f"Saved chart: severity_over_time.png\n")


# ---- inspection frequency by establishment type!!
    hist = df_valid[df_valid["source_era"] == "historical"]
    insp_per_est = (
        hist.groupby(["unified_est_id", "establishment_type"])
        .size()
        .reset_index(name="n_inspections")
    )

    type_counts = insp_per_est["establishment_type"].value_counts()
    common_types = type_counts[type_counts >= 30].index
    summary = (
        insp_per_est[insp_per_est["establishment_type"].isin(common_types)]
        .groupby("establishment_type")["n_inspections"]
        .agg(["mean", "median", "count"])
        .sort_values("mean", ascending=False)
    )

    print("=== Avg inspections per restaurant, by establishment type (30+ restaurants) ===")
    print(summary)
    print()

    fig, ax = plt.subplots(figsize=(9, 10))
    summary["mean"].sort_values().plot(kind="barh", ax=ax)
    ax.set_xlabel("Average inspections per restaurant")
    ax.set_title("Inspection frequency by establishment type")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "inspection_frequency_by_type.png"))
    plt.close(fig)
    print(f"Saved chart: inspection_frequency_by_type.png\n")

    top_type = summary.index[0]
    bottom_type = summary.index[-1]
    
# ---- checking if variance exists even within one type::

    restaurants_only = hist[hist["establishment_type"] == "Restaurant"]
    insp_counts_restaurants = restaurants_only.groupby("unified_est_id").size()

    print("=== Inspections per restaurant, within 'Restaurant' type only ===")
    print(insp_counts_restaurants.describe())
    print()
    print("\nDone.")


if __name__ == "__main__":
    main()

