"""
model.py — ML forecaster for carbon intensity.

Uses GradientBoostingRegressor with time-based features.
Two main functions:
  - train_model()       → trains on DB data, saves .pkl
  - predict_next_24h()  → loads model, predicts next 24 hours
"""

import sqlite3
import pickle
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

MODEL_PATH = os.path.join(os.path.dirname(__file__), "forecaster_model.pkl")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "greenqueue.db")


def _extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract hour, day_of_week, month, and circular hour encoding."""
    ts = pd.to_datetime(df["timestamp"])
    features = pd.DataFrame()
    features["hour"] = ts.dt.hour
    features["day_of_week"] = ts.dt.dayofweek
    features["month"] = ts.dt.month
    features["hour_sin"] = np.sin(2 * np.pi * features["hour"] / 24)
    features["hour_cos"] = np.cos(2 * np.pi * features["hour"] / 24)
    return features


def train_model() -> dict:
    """Train on all historical data, save model to disk. Returns stats dict."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT timestamp, carbon_intensity FROM carbon_readings ORDER BY timestamp", conn
    )
    conn.close()

    if len(df) < 50:
        raise ValueError(f"Need at least 50 rows, found {len(df)}")

    X = _extract_features(df)
    y = df["carbon_intensity"].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42
    )
    model.fit(X_train, y_train)

    mae = mean_absolute_error(y_test, model.predict(X_test))

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    return {"rows_used": len(df), "mae": round(mae, 2), "model_path": MODEL_PATH}


def predict_next_24h(zone: str = "US-CAL-CISO") -> list[dict]:
    """Predict carbon intensity for each of the next 24 hours."""
    # Auto-train if no model exists
    if not os.path.exists(MODEL_PATH):
        print("No saved model — training now...")
        train_model()

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    future_times = [now + timedelta(hours=i) for i in range(1, 25)]
    future_df = pd.DataFrame({"timestamp": future_times})
    preds = model.predict(_extract_features(future_df))

    return [
        {"timestamp": ts.isoformat(), "carbon_intensity": round(float(p), 1), "zone": zone}
        for ts, p in zip(future_times, preds)
    ]
