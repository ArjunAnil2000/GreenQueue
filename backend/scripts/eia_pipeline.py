import requests
import pandas as pd
from datetime import datetime, timedelta

# ===============================
# CONFIG
# ===============================

API_KEY = "TW5lNtIFe0WflaYtBLosBIaTu4NYTe3z2W4Xtsax"

end_date = datetime(2025, 8, 31)
start_date = end_date - timedelta(days=180)

start_str = start_date.strftime("%Y-%m-%dT00")
end_str   = end_date.strftime("%Y-%m-%dT23")

base_url = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"

params = {
    "frequency": "hourly",
    "data[0]": "value",
    "facets[respondent][]": "MISO",
    "start": start_str,
    "end": end_str,
    "sort[0][column]": "period",
    "sort[0][direction]": "asc",
    "offset": 0,
    "length": 100000,
    "api_key": API_KEY
}

response = requests.get(base_url, params=params)

print("Status Code:", response.status_code)

if response.status_code != 200:
    print(response.text)
    exit()

data = response.json()
records = data["response"]["data"]

df = pd.DataFrame(records)

df["value"] = pd.to_numeric(df["value"], errors="coerce")
df["period"] = pd.to_datetime(df["period"])

pivot_df = df.pivot_table(
    index="period",
    columns="fueltype",
    values="value",
    aggfunc="sum"
).reset_index()

coal_factor = 900
gas_factor = 400
oil_factor = 700

emissions = (
    pivot_df.get("COL", 0) * coal_factor +
    pivot_df.get("NG", 0) * gas_factor +
    pivot_df.get("OIL", 0) * oil_factor
)

total_generation = pivot_df.drop(columns=["period"]).sum(axis=1)

pivot_df["carbon_intensity"] = emissions / total_generation

pivot_df.to_csv("miso_carbon_6month.csv", index=False)

print("Saved 6-month carbon data.")