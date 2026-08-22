import pandas as pd
agg = pd.read_parquet("data/scored/restaurant_scores.parquet")
print("Rows in scored file:", len(agg))
print("Rows in final v2 file:", len(pd.read_parquet("data/validation/restaurant_scores_v2.parquet")))
