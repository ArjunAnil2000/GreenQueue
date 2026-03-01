import pandas as pd

df = pd.read_csv("scheduler_ready_dataset.csv")
df["datetime"] = pd.to_datetime(df["datetime"])

# Example: job duration = 4 hours
duration = 4

best_window_score = -1
best_start = None

for i in range(len(df) - duration):
    window = df.iloc[i:i+duration]
    avg_score = window["green_score"].mean()
    
    if avg_score > best_window_score:
        best_window_score = avg_score
        best_start = window.iloc[0]["datetime"]

print("Best 4-hour window starts at:", best_start)
print("Average green score:", best_window_score)