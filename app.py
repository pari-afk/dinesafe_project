#only to be run in the terminal!!

import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import requests
import json
from google import genai

gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def parse_restaurant_query(user_question):
    prompt = f"""You translate a person's plain-English restaurant search into a JSON filter. You do not answer questions about restaurant safety yourself, you only extract search criteria.

Return ONLY valid JSON, no other text, matching this exact shape:
{{
  "min_stars": <integer 1-5, or null if not mentioned>,
  "name_keyword": <a single word or short phrase from the restaurant name/cuisine type mentioned, or null>
  "sort_order": <"best_first" or "worst_first", based on what the person seems to want. Default to "best_first" if unclear>
}}

Examples:
"cheap italian food" -> {{"min_stars": null, "name_keyword": "italian", "sort_order": "best_first"}}
"only show me 4 star and above places" -> {{"min_stars": 4, "name_keyword": null, "sort_order": "best_first"}}
"safe sushi restaurants" -> {{"min_stars": 4, "name_keyword": "sushi", "sort_order": "best_first"}}
"anything decent" -> {{"min_stars": 3, "name_keyword": null}}
"worst Italian place" -> {{"min_stars": null, "name_keyword": "italian", "sort_order": "worst_first"}}
"what's the sketchiest place near me" -> {{"min_stars": null, "name_keyword": null, "sort_order": "worst_first"}}

Person's question: "{user_question}"

JSON:"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
    except Exception as e:
        print("API call failed:", e)
        return None

    raw_text = response.text.strip()
    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print("Couldn't parse JSON, raw response was:", raw_text)
        return None

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

CLEAN_COLUMNS = [
    "unified_est_id", "est_name", "address", "latitude", "longitude",
    "inspection_date", "inspection_status", "severity", "infraction_detail",
    "enforcement_action", "legal_outcome", "source_era", "has_valid_id",
]

CLEAN_CATEGORY_COLUMNS = [
    "unified_est_id", "est_name", "address", "inspection_status",
    "severity", "infraction_detail", "enforcement_action",
    "legal_outcome", "source_era",
]

STAR_COLORS = {
    5: "#4575b4",  #blue
    4: "#91bfdb",  #light blue
    3: "#ffffbf",  #yellow
    2: "#fc8d59",  #orange
    1: "#d73027",  #red
}


@st.cache_data(ttl="6h")
def load_clean():
    if os.path.exists(CLEAN_PARQUET):
        df = pd.read_parquet(CLEAN_PARQUET, columns=CLEAN_COLUMNS)
    elif os.path.exists(CLEAN_CSV):
        df = pd.read_csv(CLEAN_CSV, usecols=CLEAN_COLUMNS, parse_dates=["inspection_date"])
    else:
        st.error(f"Couldn't find dinesafe_clean.parquet or .csv in '{CLEAN_DIR}'")
        st.stop()
    for col in CLEAN_CATEGORY_COLUMNS:
        df[col] = df[col].astype("category")
    return df
    

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
    scoped["severity_weight"] = scoped["severity"].map(SEVERITY_WEIGHTS).astype("int64")
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
st.caption("See how safe Toronto restaurants really are, based on 25 years of official city health inspections.")

st.info(
    "This rating system reflects a restaurant's food safety inspection "
    "history only, not the quality of its food, service, or dining "
    "experience. A 5-star safety rating means an excellent, clean inspection "
    "record, not a 5-star dining experience. "
)

with st.expander("What do these mean?"):
    st.markdown(
        """
- 🔴 **Crucial** — a serious violation with immediate health risk (e.g. no working handwashing station)
- 🟠 **Significant** — a real risk that needs fixing soon (e.g. improper food storage temperature)
- 🟡 **Minor** — a smaller issue, often about cleanliness or record-keeping, that's still worth noting but isn't an immediate concern
- 🟢 **Clean** — no violations found during that inspection
"""
    )

df_clean = load_clean()
scores = load_scores()
scoped = build_scoped_history(df_clean)

latest_inspection = df_clean["inspection_date"].max()
if pd.notna(latest_inspection):
    st.caption(f"Data current through {latest_inspection.strftime('%B %d, %Y')}. Refreshed automatically from Toronto Open Data.")

    last_refresh = os.path.getmtime(CLEAN_PARQUET)
    last_refresh_str = pd.Timestamp(last_refresh, unit="s").strftime("%B %d, %Y at %I:%M %p")
    st.caption(f"Pipeline last refreshed: {last_refresh_str}")

tab_leaderboard, tab_trend, tab_map, tab_profile, tab_charts = st.tabs(
    ["Leaderboard", "Restaurant Trend", "Map", "Restaurant Profile", "Score Distribution"]
)

with tab_leaderboard:
    st.subheader("Search restaurants")

    col1, col2 = st.columns([3, 1])
    with col1:
        name_options = sorted(scores["est_name"].unique())
        name_filter = st.multiselect(
            "Search by name",
            name_options,
            default=[],
            placeholder="Start typing a restaurant name...",
        )
        st.caption("💡 Tip: Select one or more restaurants to compare them on the leaderboard!")
    with col2:
        star_filter = st.multiselect("Filter by stars", [5, 4, 3, 2, 1], default=[5, 4, 3, 2, 1])
        overdue_only = st.checkbox("Show only overdue-for-inspection restaurants")
        
    filtered = scores[scores["stars"].isin(star_filter)]
    if name_filter:
        filtered = filtered[filtered["est_name"].isin(name_filter)]
    if overdue_only:
        filtered = filtered[filtered["is_overdue"] == True]

    display_cols = ["est_name", "address", "stars", "n_inspections", "shrunk_avg_penalty"]
    display_cols = [c for c in display_cols if c in filtered.columns]

    st.divider()
    st.markdown("**...or just ask in plain English**")
    nl_query = st.text_input("e.g. \"Best sushi places in town\"", key="nl_search")

    if nl_query:
        with st.spinner("Thinking..."):
            parsed = parse_restaurant_query(nl_query)

        if parsed is None:
            st.warning("Sorry, I had trouble understanding that. Try rephrasing, or use the search box above instead.")
        else:
            nl_filtered = scores.copy()
            if parsed.get("min_stars"):
                nl_filtered = nl_filtered[nl_filtered["stars"] >= parsed["min_stars"]]
            if parsed.get("name_keyword"):
                nl_filtered = nl_filtered[
                    nl_filtered["est_name"].str.contains(parsed["name_keyword"], case=False, na=False)
                ]

            sort_ascending = parsed.get("sort_order") == "worst_first"


            st.caption(f"Showing results for: {parsed}")
            st.dataframe(
                nl_filtered[display_cols]
                .rename(columns={
                    "est_name": "Name",
                    "address": "Address",
                    "stars": "Stars",
                    "n_inspections": "Inspections",
                    "shrunk_avg_penalty": "Score (lower = better)",
                })
                .sort_values("Stars", ascending=sort_ascending),
                width="stretch",
                height=400,
            )

    with st.expander("Got feedback? Tell us here!"):
        feedback_text = st.text_area("Anything you'd like to flag?", key="feedback_box")
        if st.button("Submit feedback"):
            if feedback_text.strip():
                form_url = "https://docs.google.com/forms/d/e/1FAIpQLSdLOysPhBObSIof_OUnKL2sqHzNyt91ukeK1cWoi9JqRuszFg/formResponse"
                try:
                    requests.post(form_url, data={"entry.1012936315": feedback_text})
                    st.success("Thanks! Getting to your feedback after our lunch break ><")
                except Exception:
                    st.error("Oops, something went wrong! Please try again!")
            else:
                st.warning("Oops, looks like you forgot to type before submitting!")

        st.divider()

        st.markdown("**Have a concern about a specific restaurant?**")
        concern_url = "https://www.toronto.ca/community-people/health-wellness-care/health-inspections-monitoring/safe-complaints/?prog=DS"
        st.link_button("File a complaint with Toronto Public Health", concern_url)
        st.caption("This opens the City's official complaint form for quick and anonymous reporting.")

    st.write(f"{len(filtered):,} restaurants match")

    st.dataframe(
        filtered[display_cols]
        .rename(columns={
            "est_name": "Name",
            "address": "Address",
            "stars": "Stars",
            "n_inspections": "Inspections",
            "shrunk_avg_penalty": "Score (lower = better)",
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
            scores, x="shrunk_avg_penalty", nbins=50,
            labels={"shrunk_avg_penalty": "Score (lower = better)"},
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


    scoped["is_closed"] = (
        (scoped["inspection_status"] == "Closed")
        | scoped["legal_outcome"].str.contains("close", case=False, na=False)
        | (scoped["enforcement_action"] == "Closure Order")
    )
    ever_closed = (
        scoped.groupby("unified_est_id")["is_closed"]
        .any()
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
        PENALTY_CAP = 0.5
        trend_df["safety_score"] = 100 * (1 - (trend_df["score"] / PENALTY_CAP).clip(upper=1))

        fig = px.line(
            trend_df, x="year", y="safety_score", markers=True,
            labels={"safety_score": "Safety score (0-100, higher is better)", "year": "Year"},
            title=f"Score trend: {hist['est_name'].iloc[-1]}",
        )
        st.plotly_chart(fig, width="stretch")

with tab_profile:
    st.subheader("Restaurant profile")
    st.caption("Full inspection history for any currently-operating restaurant.")

    profile_search = st.selectbox(
        "Search by restaurant name",
        scores["est_name"] + " — " + scores["address"],
        index=None,
        placeholder="Search for a restaurant",
        key="profile_search",
    )

    if profile_search:
        chosen_id = scores.loc[
            (scores["est_name"] + " — " + scores["address"] == profile_search),
            "unified_est_id",
        ].iloc[0]
        chosen_score = scores.loc[scores["unified_est_id"] == chosen_id].iloc[0]

        #header card
        col_a, col_b, col_c = st.columns([3, 1, 1])
        with col_a:
            st.markdown(f"### {chosen_score['est_name']}")
            st.write(chosen_score["address"])
        with col_b:
            stars_display = "⭐" * int(chosen_score["stars"])
            st.metric("Safety Rating", stars_display)
            st.caption("Based on health inspections, not a dining review!")
        with col_c:
            st.metric("Total inspections", int(chosen_score["n_inspections"]))

        st.divider()
        if chosen_score.get("is_overdue"):
            st.warning(
                f"This restaurant hasn't been inspected in {int(chosen_score['days_since_last'])} days, "
                f"longer than its usual gap of about {int(chosen_score['typical_gap'])} days. "
                f"It is among the 5% most overdue currently-operating restaurants."
            )

        concern_url = "https://www.toronto.ca/community-people/health-wellness-care/health-inspections-monitoring/safe-complaints/?prog=DS"
        st.link_button("Flag a concern about this restaurant", concern_url)
        st.caption(
            f"Opens Toronto Public Health's official complaint form. "
            f"Mention \"{chosen_score['est_name']}\" and the address above when filling it out."
        )

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

        #inspection timeline
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
        st.write("Select a restaurant above to view its profile.")
