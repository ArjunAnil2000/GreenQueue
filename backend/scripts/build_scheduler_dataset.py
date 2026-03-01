import pandas as pd

# Load datasets
nasa_df = pd.read_csv("renewable_6month_extended.csv")
carbon_df = pd.read_csv("miso_carbon_6month.csv")

nasa_df["datetime"] = pd.to_datetime(nasa_df["datetime"])
carbon_df["period"] = pd.to_datetime(carbon_df["period"])
carbon_df = carbon_df.rename(columns={"period": "datetime"})

# Merge
combined_df = nasa_df.merge(
    carbon_df[["datetime", "carbon_intensity"]],
    on="datetime",
    how="inner"
)

print("Merged shape:", combined_df.shape)

# Normalize carbon (lower carbon = higher score)
combined_df["carbon_norm"] = (
    combined_df["carbon_intensity"].max()
    - combined_df["carbon_intensity"]
) / (
    combined_df["carbon_intensity"].max()
    - combined_df["carbon_intensity"].min()
)

# Combined green score
combined_df["green_score"] = (
    0.6 * combined_df["carbon_norm"]
    + 0.4 * combined_df["renewable_index"]
)

# Sort best hours
best_hours = combined_df.sort_values("green_score", ascending=False)

print("\nTop 10 greenest hours:")
print(best_hours[["datetime", "renewable_index",
                  "carbon_intensity", "green_score"]].head(10))

combined_df.to_csv("scheduler_ready_dataset.csv", index=False)

print("\nSaved scheduler_ready_dataset.csv")