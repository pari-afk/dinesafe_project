# Toronto Restaurant Safety Scores

A 1-5 star safety rating for every restaurant currently operating in Toronto, built from 25 years of city inspection data (2001-2026). Instead of just averaging violations, the score accounts for how serious each violation was, how long ago it happened, how often the restaurant actually gets inspected, and whether there's enough inspection history to trust the result.

## Why not just average the violations?

That's the obvious first approach, and it's also pretty broken. A few things I ran into while exploring the data:

Inspection frequency is wildly uneven. Nursing homes get checked about 66 times on average. Fairs and festivals get checked about once. If you just count violations, you're punishing places that get watched closely and rewarding places nobody bothers to inspect.

Not every violation is the same. A "Crucial" infraction (the kind that can shut a place down) and a "Minor" one shouldn't be worth the same amount.

Old violations shouldn't haunt a restaurant forever. Something that happened in 2009 matters less than something from last year, especially if the place has been clean since.

And small sample sizes lie to you. A restaurant inspected once, which happened to pass, isn't the same as a restaurant inspected 50 times with a clean record. I actually found this exact problem mid-project — more on that below.

## The data

Toronto publishes this as 23 separate files: 22 yearly files from 2001-2022, plus one rolling file that covers late 2023 through now. The two eras don't use the same column names, and some fields exist in one era but not the other. So step one was just figuring out how these fit together before doing anything else.

Once unified: about 460,000 inspection records, roughly 22,000 restaurants across the full 25-year span, about 16,000 of which are still open today.

## How I built it

1. Audited every file before writing any pipeline code. Found that pandas chokes on three of the files in a way that looked like a structural problem but turned out to be a single stray quote character at the very end of one file. Worth knowing before you trust any "this CSV is broken" assumption.
2. Built a pipeline to unify both schema eras, including figuring out that oldEstId in the current file is the same ID system as Establishment ID in the old files - that's the key that lets you track one restaurant's history across the schema change.
3. Cleaned it up. Severity shows up as "no value" in four different ways in the raw data. Collapsed those into one category, but kept it as a real outcome, not missing data, since it usually just means nothing was flagged.
4. Explored it before building any formula, specifically to check whether inspection frequency was actually as skewed as I suspected. It was - about a 50x gap between the most and least inspected categories. That's what convinced me normalization wasn't optional.
5. Built the scoring formula.
6. Validated it - and caught a real bug in my own first version. See below.
7. Built a dashboard so the scores are actually usable, not just sitting in a CSV.

## The scoring formula

Every violation gets a weight based on severity: Crucial = 5, Significant = 2, Minor = 1, nothing flagged = 0.

That weight decays over time with a 2.5-year half-life - a violation from five years ago counts for about a quarter of what it would if it happened today.

Total penalty gets divided by how many times the restaurant has actually been inspected, so a place checked 80 times isn't unfairly compared to one checked twice.

Then each restaurant's score gets pulled slightly toward the city-wide average if it doesn't have much inspection history yet. The pull is strong for a restaurant with one inspection and basically nothing for a restaurant with fifty.

Finally, restaurants get sorted into 1-5 stars based on where their score falls in the real distribution, not some made-up cutoff.

## The bug I found

My first version of this formula looked completely fine when I built it. Then I checked something I almost didn't bother checking: how many inspections did 5-star restaurants actually have on average?

Turned out 5-star restaurants had fewer inspections on average than every other tier, including 1-star. About 1 in 5 of them had been inspected exactly once. A restaurant could get the best possible score just by being lucky enough to be checked a single time and pass, which isn't the same thing as actually having a good track record.

Fixed it by pulling low-inspection restaurants' scores toward the average before assigning stars, weighted by how little data they actually have. After the fix, the minimum number of inspections needed to hit 5 stars went from 1 to 8, and 96% of 5-star restaurants now have at least 10 inspections behind them.

## Does the score actually mean anything?

Two checks, both of which held up:

- Restaurants rated 1-star have on average about 2x the raw violation severity of 5-star restaurants.
- 1.6% of 1-star restaurants have been forcibly closed by the city at some point. Exactly 0% of 5-star restaurants have.

I also spot-checked a handful of well-known chains and individual locations spread across the full range of star ratings rather than all clumping at one score, which makes sense since each location is independently run and inspected.

To be honest about the limits: the 3-star and 4-star tiers are close to each other on inspection volume, and the map shows lower scores clustering a bit downtown, which might just mean downtown gets inspected more often, not that the food is actually worse there.

## Running it yourself

pip install streamlit pandas numpy plotly pyarrow

cd dinesafe-project

streamlit run app.py

Opens up in your browser. Four tabs: a searchable leaderboard, score distribution charts, a map of restaurants colored by rating, and a trend view that shows how any single restaurant's score has shifted year by year.

## What is in here

- 01_audit_and_schema.py
- 02_ingestion_pipeline.py
- 03_data_cleaning.py
- 04_eda.py
- 05_scoring.py
- 06_validation.py
- app.py
- requirements.txt
- data/processed/ - cleaned dataset
- data/validation/ - final scores and validation charts
- data/eda/ - exploratory charts

## Built with

Python, pandas, numpy, Streamlit, Plotly.

## Source

City of Toronto DineSafe Open Data - https://open.toronto.ca/dataset/dinesafe/
