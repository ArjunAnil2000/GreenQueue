import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# ===============================
# CONFIG
# ===============================

latitude = 43.0731      # Madison, WI
longitude = -89.4012

# 6-month historical window
end_date = datetime(2025, 8, 31)
start_date = end_date - timedelta(days=180)

start = start_date.strftime("%Y%m%d")
end = end_date.strftime("%Y%m%d")

print("Fetching data from:", start, "to", end)

# ===============================
# NASA POWER API CALL
# ===============================

url = (
    "https://power.larc.nasa.gov/api/temporal/hourly/point?"
    f"latitude={latitude}&longitude={longitude}"
    f"&start={start}&end={end}"
    "&parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,WS50M,CLOUD_AMT,T2M"
    "&community=RE"
    "&format=JSON"
)

response = requests.get(url)
print("Status Code:", response.status_code)

if response.status_code != 200:
    print("API request failed.")
    exit()

data = response.json()["properties"]["parameter"]

# ===============================
# BUILD DATAFRAME
# ===============================

df = pd.DataFrame({
    "datetime": data["ALLSKY_SFC_SW_DWN"].keys(),
    "solar": data["ALLSKY_SFC_SW_DWN"].values(),
    "clear_sky_solar": data["CLRSKY_SFC_SW_DWN"].values(),
    "wind50": data["WS50M"].values(),
    "cloud": data["CLOUD_AMT"].values(),
    "temp": data["T2M"].values()
})

df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d%H")
df = df.sort_values("datetime")

# ===============================
# CLEAN DATA
# ===============================

for col in ["solar", "clear_sky_solar", "wind50", "cloud", "temp"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Remove NASA missing values (-999)
df = df[(df["solar"] >= 0) & (df["wind50"] >= 0)]
df = df.dropna()

print("After cleaning:", df.shape)
# ===============================
# FEATURE ENGINEERING (SAFE VERSION)
# ===============================

# Solar attenuation ratio (handle divide-by-zero properly)
df["solar_ratio"] = df["solar"] / df["clear_sky_solar"]
df["solar_ratio"] = df["solar_ratio"].replace([float("inf"), -float("inf")], pd.NA)

# Cloud-adjusted effective solar
df["solar_effective"] = df["solar"] * (1 - df["cloud"] / 100)

# Normalize features
df["solar_eff_norm"] = df["solar_effective"] / df["solar_effective"].max()
df["wind_norm"] = df["wind50"] / df["wind50"].max()
df["clear_ratio_norm"] = df["solar_ratio"] / df["solar_ratio"].max()

# ===============================
# RENEWABLE INDEX
# ===============================

df["renewable_index"] = (
    0.5 * df["solar_eff_norm"] +
    0.3 * df["wind_norm"] +
    0.2 * df["clear_ratio_norm"]
)

# Remove any remaining invalid rows
df = df.replace([float("inf"), -float("inf")], pd.NA)
df = df.dropna(subset=["renewable_index"])

print("After final cleaning:", df.shape)

# ===============================
# PLOT
# ===============================

plt.figure(figsize=(12,5))
plt.plot(df["datetime"], df["renewable_index"])
plt.title("Improved Renewable Availability Index")
plt.xlabel("Time")
plt.ylabel("Renewable Index")
plt.tight_layout()
plt.show()

# ===============================
# SAVE DATA
# ===============================

df.to_csv("renewable_6month_extended.csv", index=False)
print("\nSaved to renewable_6month_extended.csv")