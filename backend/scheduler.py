"""
scheduler.py — Finds the greenest time window for a job using ML forecasts,
               and provides a background execution simulator.
"""

from model import predict_next_24h


def suggest_green_windows(horizon_hours: int = 6, zone: str = "US-CAL-CISO") -> list[dict]:
    """
    Search the next `horizon_hours` of forecast for the single greenest
    hour to start the job.  Returns top 3 one-hour slots with savings
    info. `horizon_hours` = how long the user is willing to wait.
    """
    forecast = predict_next_24h(zone)

    # Clamp horizon to available forecast length
    horizon = min(horizon_hours, len(forecast))
    if horizon < 1:
        horizon = 1

    # "Naive" carbon = intensity if run right now (first hour)
    naive_avg = forecast[0]["carbon_intensity"]

    # Evaluate each hour within the horizon as a candidate start time
    windows = []
    for i in range(horizon):
        h = forecast[i]
        windows.append({
            "start": h["timestamp"],
            "end": h["timestamp"],
            "avg_carbon": round(h["carbon_intensity"], 1),
            "hours": [h],
        })

    # Sort by average carbon (lowest = greenest)
    windows.sort(key=lambda w: w["avg_carbon"])

    # Find worst window for savings calculation
    worst_avg = windows[-1]["avg_carbon"] if windows else 0

    # Return top 3 with rank, savings, and naive comparison
    results = []
    for i, w in enumerate(windows[:3]):
        w["rank"] = i + 1
        w["savings_vs_worst"] = round(worst_avg - w["avg_carbon"], 1)
        w["naive_carbon"] = round(naive_avg, 1)
        w["savings_vs_naive"] = round(naive_avg - w["avg_carbon"], 1)
        results.append(w)

    return results
