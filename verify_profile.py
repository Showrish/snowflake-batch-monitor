"""Independent check of the source file in pandas. Put Laboratory.csv next to this script.
Each comment shows the expected output, which the Snowflake checks also reproduce."""
import pandas as pd

df = pd.read_csv("Laboratory.csv", sep=";", dtype=str)
print(len(df), df["batch"].nunique())               # 1005 1005
print(sorted(df["start"].str[:3].unique()))          # includes maj, avg, okt (Slovenian months)
print((df["api_water"].str.strip() == "").sum())     # 26 blanks stored as spaces
print(df["strength"].unique())                       # 5MG, 10M, 20M, 40M
print(df["tbl_min_weight"].isna().sum())             # 10 missing tablet weights
d = pd.to_numeric(df["dissolution_av"])
print(round(d.mean(), 3), d.min(), d.max())          # 90.65 82.5 102.67
