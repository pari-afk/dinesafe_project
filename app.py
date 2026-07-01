#only to be run in the terminal!!

import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px


CLEAN_DIR = "data/processed"
SCORES_DIR = "data/validation"


CLEAN_PARQUET = os.path.join(CLEAN_DIR, "dinesafe_clean.parquet")
CLEAN_CSV = os.path.join(CLEAN_DIR, "dinesafe_clean.csv")
SCORES_PARQUET = os.path.join(SCORES_DIR, "restaurant_scores_v2.parquet")
SCORES_CSV = os.path.join(SCORES_DIR, "restaurant_scores_v2.csv")

SEVERITY_WEIGHTS = {
    "C - Crucial": 5,
    "S - Significant": 2,
    "M - Minor": 1,
    "NO_SEVERITY": 0,
}
HALF_LIFE_YEARS = 2.5
SHRINKAGE_K = 5

STAR_COLORS = {
    5: "#1a9850",
    4: "#91cf60",
    3: "#fee08b",
    2: "#fc8d59",
    1: "#d73027",
}


@st.cache_data
def load_clean():
    if os.path.exists(CLEAN_PARQUET):
        return pd.read_parquet(CLEAN_PARQUET)
    elif os.path.exists(CLEAN_CSV):
        return pd.read_csv(CLEAN_CSV, parse_dates=["inspection_date"])
    else:
        st.error(f"Couldn't find dinesafe_clean.parquet or .csv in '{CLEAN_DIR}'")
        st.stop()


@st.cache_data
def load_scores():
    if os.path.exists(SCORES_PARQUET):
        return pd.read_parquet(SCORES_PARQUET)
    elif os.path.exists(SCORES_CSV):
        return pd.read_csv(SCORES_CSV)
    else:
        st.error(f"Couldn't find restaurant_scores_v2.parquet or .csv in '{SCORES_DIR}'")
        st.stop()


@st.cache_data
def build_scoped_history(_df_clean):
    df_valid = _df_clean[_df_clean["has_valid_id"]].copy()
    current_ids = set(
        df_valid.loc[df_valid["source_era"] == "current", "unified_est_id"]
    )
    scoped = df_valid[df_valid["unified_est_id"].isin(current_ids)].copy()
    scoped["severity_weight"] = scoped["severity"].map(SEVERITY_WEIGHTS)
    return scoped


def global_mean_penalty(scoped, anchor_date):
    h = scoped[scoped["inspection_date"] <= anchor_date]
    if len(h) == 0:
        return 0.0
    years_ago = (anchor_date - h["inspection_date"]).dt.days / 365.25
    decay = 0.5 ** (years_ago / HALF_LIFE_YEARS)
    penalty = (h["severity_weight"] * decay).sum()
    return penalty / len(h)


def score_as_of(history_df, anchor_date, g_mean):
    h = history_df[history_df["inspection_date"] <= anchor_date]
    n = len(h)
    if n == 0:
        return None
    years_ago = (anchor_date - h["inspection_date"]).dt.days / 365.25
    decay = 0.5 ** (years_ago / HALF_LIFE_YEARS)
    penalty = (h["severity_weight"] * decay).sum()
    return (penalty + SHRINKAGE_K * g_mean) / (n + SHRINKAGE_K)


st.set_page_config(page_title="Toronto Restaurant Safety Scores", layout="wide")
st.title("Toronto Restaurant Safety Scores")
st.caption(
    "A severity-weighted, recency-decayed, inspection-count-normalized "
    "1-5 star rating built from 25 years of Toronto DineSafe inspection "
    "records (2001-2026)."
)

df_clean = load_clean()
scores = load_scores()
scoped = build_scoped_history(df_clean)

tab_leaderboard, tab_charts, tab_map, tab_trend, tab_profile = st.tabs(
    ["Leaderboard", "Score Distribution", "Map", "Restaurant Trend", "Restaurant Profile"]
)

with tab_leaderboard:
    st.subheader("Search restaurants")

    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("Search by name", "")
    with col2:
        star_filter = st.multiselect("Filter by stars", [5, 4, 3, 2, 1], default=[5, 4, 3, 2, 1])

    filtered = scores[scores["stars"].isin(star_filter)]
    if search_term:
        filtered = filtered[
            filtered["est_name"].str.contains(search_term, case=False, na=False)
        ]

    st.write(f"{len(filtered):,} restaurants match")

    display_cols = ["est_name", "address", "stars", "n_inspections", "adjusted_penalty"]
    display_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(
        filtered[display_cols]
        .rename(columns={
            "est_name": "Name",
            "address": "Address",
            "stars": "Stars",
            "n_inspections": "Inspections",
            "adjusted_penalty": "Score (lower = better)",
        })
        .sort_values("Stars", ascending=False),
        width="stretch",
        height=500,
    )

with tab_charts:
    st.subheader("How scores are distributed")

    col1, col2 = st.columns(2)

    with col1:
        fig = px.histogram(
            scores, x="adjusted_penalty", nbins=50,
            labels={"adjusted_penalty": "Adjusted penalty (lower = better)"},
            title="Distribution of restaurant scores",
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        star_counts = scores["stars"].value_counts().sort_index()
        fig = px.bar(
            x=star_counts.index, y=star_counts.values,
            labels={"x": "Star rating", "y": "Number of restaurants"},
            title="Restaurants per star rating",
            color=star_counts.index.astype(str),
            color_discrete_map={str(k): v for k, v in STAR_COLORS.items()},
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")

    st.subheader("Validation: does the score track real risk?")

    merged = scoped.merge(scores[["unified_est_id", "stars"]], on="unified_est_id")
    severity_by_star = merged.groupby("stars")["severity_weight"].mean().sort_index()


    ever_closed = (
        scoped.groupby("unified_est_id")["inspection_status"]
        .apply(lambda x: (x == "Closed").any())
        .reset_index(name="ever_closed")
    )
    scores_for_merge = scores.drop(columns=["ever_closed"], errors="ignore")
    closed_check = scores_for_merge.merge(ever_closed, on="unified_est_id")
    closed_by_star = (closed_check.groupby("stars")["ever_closed"].mean() * 100).sort_index()

    col3, col4 = st.columns(2)
    with col3:
        fig = px.bar(
            x=severity_by_star.index, y=severity_by_star.values,
            labels={"x": "Star rating", "y": "Avg raw severity weight"},
            title="Severity exposure drops as stars rise",
        )
        st.plotly_chart(fig, width="stretch")
    with col4:
        fig = px.bar(
            x=closed_by_star.index, y=closed_by_star.values,
            labels={"x": "Star rating", "y": "% ever marked 'Closed'"},
            title="Closure rate drops as stars rise",
        )
        st.plotly_chart(fig, width="stretch")

with tab_map:
    st.subheader("Restaurants by location and star rating")

    map_star_filter = st.multiselect(
        "Show stars", [5, 4, 3, 2, 1], default=[1, 2], key="map_filter"
    )
    st.caption("Defaults to showing 1 and 2 star restaurants - the ones worth knowing about.")

    latest_location = (
        scoped.sort_values("inspection_date")
        .groupby("unified_est_id")[["latitude", "longitude"]]
        .last()
        .reset_index()
    )
    map_df = scores.merge(latest_location, on="unified_est_id")
    map_df = map_df[map_df["stars"].isin(map_star_filter)]

    fig = px.scatter_mapbox(
        map_df,
        lat="latitude",
        lon="longitude",
        color="stars",
        hover_name="est_name",
        hover_data={"address": True, "n_inspections": True, "stars": True,
                    "latitude": False, "longitude": False},
        color_continuous_scale=[STAR_COLORS[s] for s in sorted(STAR_COLORS)],
        zoom=10,
        height=600,
    )
    fig.update_layout(mapbox_style="open-street-map", margin={"l": 0, "r": 0, "t": 0, "b": 0})
    st.plotly_chart(fig, width="stretch")

with tab_trend:
    st.subheader("How has this restaurant's score changed over time?")
    st.caption(
        "Recomputes the score as if 'today' were Dec 31 of each year, "
        "using only the inspection history available up to that point. "
        "Only restaurants with at least 5 years of history are listed, "
        "so the trend line is actually meaningful."
    )

    history_span = (
        scoped.groupby("unified_est_id")["inspection_date"]
        .agg(lambda x: x.max().year - x.min().year)
    )
    eligible_ids = history_span[history_span >= 5].index
    eligible = scores[scores["unified_est_id"].isin(eligible_ids)].sort_values("est_name")

    chosen_name = st.selectbox(
        "Choose a restaurant",
        eligible["est_name"] + " — " + eligible["address"],
    )

    if chosen_name:
        chosen_id = eligible.iloc[
            (eligible["est_name"] + " — " + eligible["address"] == chosen_name).values
        ]["unified_est_id"].iloc[0]

        hist = scoped[scoped["unified_est_id"] == chosen_id].sort_values("inspection_date")
        start_year = hist["inspection_date"].min().year
        end_year = hist["inspection_date"].max().year

        years = list(range(start_year, end_year + 1))
        trend_rows = []
        for y in years:
            anchor = pd.Timestamp(f"{y}-12-31")
            g_mean = global_mean_penalty(scoped, anchor)
            score = score_as_of(hist, anchor, g_mean)
            if score is not None:
                trend_rows.append({"year": y, "score": score})

        trend_df = pd.DataFrame(trend_rows)

        fig = px.line(
            trend_df, x="year", y="score", markers=True,
            labels={"score": "Adjusted penalty (lower = better)", "year": "Year"},
            title=f"Score trend: {hist['est_name'].iloc[-1]}",
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "Note: the y-axis is reversed so an upward-trending line means "
            "the restaurant's record is improving over time."
        )

with tab_profile:
    st.subheader("Restaurant profile")
    st.caption("Full inspection history for any currently-operating restaurant.")

#searchable options
    profile_search = st.text_input("Search by restaurant name", "", key="profile_search")

    if profile_search:
        matches = scores[
            scores["est_name"].str.contains(profile_search, case=False, na=False)
        ].sort_values("stars", ascending=False)

        if matches.empty:
            st.write("No restaurants found matching that name.")
        else:
            #if multiple locations, let user pick one
            label_options = matches["est_name"] + " — " + matches["address"]
            chosen_label = st.selectbox("Select a location", label_options)

            chosen_id = matches.iloc[
                (label_options == chosen_label).values
            ]["unified_est_id"].iloc[0]

            chosen_score = matches.iloc[
                (label_options == chosen_label).values
            ].iloc[0]

            #header card
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.markdown(f"### {chosen_score['est_name']}")
                st.write(chosen_score["address"])
            with col_b:
                stars_display = "⭐" * int(chosen_score["stars"])
                st.metric("Rating", stars_display)
            with col_c:
                st.metric("Total inspections", int(chosen_score["n_inspections"]))

            st.divider()

            #pull full history for this restaurant 
            hist = scoped[
                scoped["unified_est_id"] == chosen_id
            ].copy().sort_values("inspection_date", ascending=False)

            #severity badge 
            sev_counts = hist["severity"].value_counts()
            crucial = sev_counts.get("C - Crucial", 0)
            significant = sev_counts.get("S - Significant", 0)
            minor = sev_counts.get("M - Minor", 0)
            clean = sev_counts.get("NO_SEVERITY", 0)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🔴 Crucial", crucial)
            col2.metric("🟠 Significant", significant)
            col3.metric("🟡 Minor", minor)
            col4.metric("🟢 Clean inspections", clean)

            st.divider()

            # --- inspection timeline ---
            st.markdown("#### Inspection history")

            cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=5)
            recent = hist[hist["inspection_date"] >= cutoff_date]
            older = hist[hist["inspection_date"] < cutoff_date]

            def render_timeline(df_slice):
                for _, row in df_slice.iterrows():
                    date_str = row["inspection_date"].strftime("%b %d, %Y")
                    sev = row["severity"]
                    detail = row["infraction_detail"]
                    status = row["inspection_status"]

                    if sev == "NO_SEVERITY":
                        icon = "🟢"
                        sev_label = "Clean"
                    elif sev == "C - Crucial":
                        icon = "🔴"
                        sev_label = "Crucial"
                    elif sev == "S - Significant":
                        icon = "🟠"
                        sev_label = "Significant"
                    else:
                        icon = "🟡"
                        sev_label = "Minor"

                    with st.container():
                        col_icon, col_content = st.columns([1, 11])
                        with col_icon:
                            st.write(icon)
                        with col_content:
                            st.markdown(
                                f"**{date_str}** &nbsp;·&nbsp; {sev_label} &nbsp;·&nbsp; *{status}*"
                            )
                            if pd.notna(detail) and detail != "" and sev != "NO_SEVERITY":
                                st.caption(detail)
            st.markdown(f"**Last 5 years** ({len(recent)} inspection records)")
            render_timeline(recent)

            if not older.empty:
                with st.expander(f"Show older history ({len(older)} records before {cutoff_date.strftime('%Y')})"):
                    render_timeline(older)
    else:
        st.write("Type a restaurant name above to view its profile.")

