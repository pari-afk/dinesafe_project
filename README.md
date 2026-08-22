# Toronto Restaurant Safety Scores

A 1-5 star safety rating for every restaurant currently operating in Toronto, built from 25 years of city inspection data (2001-2026) and refreshed automatically every day. Instead of just averaging violations, the score accounts for how serious each violation was, how long ago it happened, how often the restaurant actually gets inspected, and whether there's enough inspection history to trust the result.

## Why not just average the violations?

That's the obvious first approach, and it's also pretty broken. A few things I ran into while exploring the data:

Inspection frequency is wildly uneven. Nursing homes get checked about 66 times on average. Fairs and festivals get checked about once. If you just count violations, you're punishing places that get watched closely and rewarding places nobody bothers to inspect.

Not every violation is the same. A "Crucial" infraction (the kind that can shut a place down) and a "Minor" one shouldn't be worth the same amount.

Old violations shouldn't haunt a restaurant forever. Something that happened in 2009 matters less than something from last year, especially if the place has been clean since.

And small sample sizes lie to you. A restaurant inspected once, which happened to pass, isn't the same as a restaurant inspected 50 times with a clean record. I actually found this exact problem mid-project, more on that below.

## Restaurants only, not every food premise

DineSafe's data covers every licensed food premise in the city, not just restaurants. That includes nursing homes, daycares, schools, hospitals, banquet halls, food processing plants, and dozens of other categories that most people wouldn't think of as "a restaurant" when they open an app called Restaurant Safety Scores.

Filtering that down turned out to be harder than expected. The historical files (2001-2022) include a clean `Establishment Type` field. The live current-era feed, the one the daily refresh actually pulls from, doesn't include that field at all. I confirmed this by checking the API's own documentation for that field, which describes it as "category of infraction," not establishment type.

The fix has three layers:

1. For restaurants with a historical record, borrow the establishment type from their own past inspections.
2. For restaurants with no historical record (mostly newer businesses), check them against a list I built combining automated name/chain matching with manual research, since I personally verified a sample of ambiguous names against real addresses.
3. Anything still unresolved gets excluded rather than guessed at.

This means very recently opened restaurants with no prior inspection history and no clear name match might not show up yet. That's a real, known gap, not a hidden one.

## Keeping it live

The dashboard used to run on a data snapshot I'd download by hand. It now pulls fresh data on its own.

A scheduled GitHub Action (`.github/workflows/refresh-data.yml`) runs the full pipeline daily: fetch the current DineSafe data straight from Toronto's Open Data API, re-run ingestion, cleaning, scoring, and validation, and commit the result if anything changed. Streamlit Community Cloud watches this repo and redeploys automatically on every new commit, so a successful scheduled run is what actually keeps the live dashboard current, not just a cron job running quietly with nothing downstream.

`00_fetch_live_data.py` handles the fetch itself. Toronto's Open Data portal is a CKAN instance, and the specific file behind a dataset can get swapped out with a new ID whenever the City refreshes it, so the script always asks the API for the current resource list rather than hardcoding one.

## The data

Toronto publishes this as 23 separate files: 22 yearly files from 2001-2022, plus one rolling file that covers late 2023 through now. The two eras don't use the same column names, and some fields exist in one era but not the other.

Once unified and filtered to restaurants only: about 8,700 restaurants currently open in the city, drawn from roughly 22,000 food premises tracked across the full 25-year span.

## How I built it

Audited every file before writing any pipeline code. Found that pandas chokes on three of the files in a way that looked like a structural problem but turned out to be a single stray quote character at the very end of one file. Worth knowing before you trust any "this CSV is broken" assumption.

Built a pipeline to unify both schema eras, including figuring out that `oldEstId` in the current file is the same ID system as `Establishment ID` in the old files, which is the key that lets you track one restaurant's history across the schema change.

Cleaned it up. Severity shows up as "no value" in four different ways in the raw data. Collapsed those into one category, but kept it as a real outcome, not missing data, since it usually just means nothing was flagged.

Explored it before building any formula, specifically to check whether inspection frequency was actually as skewed as I suspected. It was, about a 50x gap between the most and least inspected categories. That's what convinced me normalization wasn't optional.

Built the scoring formula. Validated it, and caught a real bug in my own first version. See below.

Built a dashboard so the scores are actually usable, not just sitting in a CSV.

## The scoring formula

Every violation gets a weight based on severity: Crucial = 5, Significant = 2, Minor = 1, nothing flagged = 0.

That weight decays over time with a 2.5-year half-life, so a violation from five years ago counts for about a quarter of what it would if it happened today.

Total penalty gets divided by how many times the restaurant has actually been inspected, so a place checked 80 times isn't unfairly compared to one checked twice.

Then each restaurant's score gets pulled toward the city-wide average if it doesn't have much inspection history yet. The pull is strong for a restaurant with a couple of inspections and basically nothing for a restaurant with fifty.

Finally, restaurants get sorted into 1-5 stars based on where their score falls in the real distribution, not some made-up cutoff.

## The bug I found

My first version of this formula looked completely fine when I built it. Then I checked something I almost didn't bother checking: how many inspections did 5-star restaurants actually have on average?

Turned out 5-star restaurants had fewer inspections on average than every other tier, including 1-star. A restaurant could get the best possible score just by being lucky enough to be checked a single time and pass, which isn't the same thing as actually having a good track record.

Fixed it by pulling low-inspection restaurants' scores toward the average before assigning stars, weighted by how little data they actually have. As the restaurant population has grown through the live refresh and the restaurant-type filtering work, that minimum threshold has moved, currently sitting at 6 inspections to reach 5 stars, which is itself a sign the fix is doing its job as new restaurants join the dataset over time rather than a fixed number I'm holding constant.

## Does the score actually mean anything?

Restaurants rated 1-star show roughly 80% more raw violation severity on average than 5-star restaurants, and that gap holds at both extremes. The middle tiers don't always fall in perfectly increasing order, since some of those tiers include a lot of recently added restaurants with limited inspection history, which adds some noise to any single tier's average without breaking the overall pattern.

Closure rate tells a similar but noisier story. 1-star restaurants have a meaningfully higher rate of having ever been forcibly closed than 3, 4, or 5-star restaurants. I won't claim it's a clean, perfectly ordered gradient though, since actual closures are rare events, well under 1% of restaurants overall, and restricting the dataset to restaurants only (instead of every food premise) shrunk the number of closure events available to validate against. Small numbers get noisy. That's a real limitation, not something I'm papering over.

I also spot-checked well-known chains like Tim Hortons and Pizza Pizza, individual locations spread across the full range of star ratings rather than all clumping at one score, which makes sense since each location is independently run and inspected.

To be honest about the limits: the map shows lower scores clustering a bit downtown, which might just mean downtown gets inspected more often, not that the food is actually worse there.

## Overdue for inspection

Beyond the star rating itself, restaurants get flagged if they're significantly overdue for inspection relative to their own normal pattern, not some fixed number applied to everyone. A restaurant that's usually inspected every 3 months and hasn't been checked in 8 gets flagged; a restaurant that's normally checked once a year isn't penalized for a gap that's actually typical for it.

This flags the most overdue 5% of restaurants, currently a ratio of about 4.9x their own typical gap. The idea comes from resource-prioritization work public health departments have actually done, most notably Chicago's, which used inspection history to help decide where limited inspection capacity should go next, rather than trying to predict exactly when an inspector will show up.

## Ask it in plain English

There's a natural language search box on the leaderboard, backed by an LLM (Gemini) that translates a plain question like "cheap Italian food with a good safety record" into a real filter over the actual scored data. The model's only job is translation. It never generates a claim about whether a restaurant is safe; that answer always comes from the real, already-computed scores, never from the model's own reasoning.

## What the stars don't mean

Worth saying directly, since it's an easy thing to misread: this rating reflects food safety inspection history, not food quality, service, or the dining experience. A 5-star safety rating means an excellent, clean inspection record. It doesn't mean the food is good.

## Running it yourself
pip install -r requirements.txt
cd dinesafe-project
streamlit run app.py


Opens up in your browser. Five tabs: a searchable leaderboard with plain-English search, a restaurant trend view showing how any single restaurant's score has shifted year by year, a map colored by rating, a full restaurant profile with inspection-by-inspection history, and score distribution charts.

To pull fresh data yourself instead of using what's committed, run `python 00_fetch_live_data.py` before the rest of the pipeline.

## What is in here

- `00_fetch_live_data.py` - pulls current data from Toronto's Open Data API
- `01_audit_and_schema.py`
- `02_ingestion_pipeline.py`
- `03_data_cleaning.py`
- `04_eda.py`
- `05_scoring.py`
- `06_validation.py`
- `app.py`
- `requirements.txt`
- `.github/workflows/refresh-data.yml` - scheduled pipeline run and auto-commit
- `data/raw/` - source CSVs, historical files plus the live-refreshed current file
- `data/processed/` - cleaned dataset
- `data/manual/` - manually verified restaurant classifications
- `data/scored/` - raw scoring output
- `data/validation/` - final scores, overdue flags, and validation charts
- `data/eda/` - exploratory charts

## Built with

Python, pandas, numpy, Streamlit, Plotly, GitHub Actions, Google Gemini.

## Source

City of Toronto DineSafe Open Data - https://open.toronto.ca/dataset/dinesafe/
