"""
scheduler.py — Finds the greenest time window for a job using ML forecasts,
               and provides a background execution simulator.
"""

from model import predict_next_24h


def suggest_green_windows(duration_hours: int = 1, zone: str = "US-CAL-CISO") -> list[dict]:
    """
    Slide a window across the next 24h forecast and return the top 3
    greenest (lowest avg carbon) windows. Also computes naive_carbon —
    what the intensity would be if you ran the job right now.
    """
    forecast = predict_next_24h(zone)

    if duration_hours > len(forecast):
        duration_hours = len(forecast)

    # "Naive" carbon = avg intensity of the FIRST window (run immediately)
    naive_hours = forecast[:duration_hours]
    naive_avg = sum(h["carbon_intensity"] for h in naive_hours) / len(naive_hours)

    # Slide a window of size `duration_hours` across the 24 predictions
    windows = []
    for i in range(len(forecast) - duration_hours + 1):
        window_hours = forecast[i : i + duration_hours]
        avg = sum(h["carbon_intensity"] for h in window_hours) / len(window_hours)
        windows.append({
            "start": window_hours[0]["timestamp"],
            "end": window_hours[-1]["timestamp"],
            "avg_carbon": round(avg, 1),
            "hours": window_hours,
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
