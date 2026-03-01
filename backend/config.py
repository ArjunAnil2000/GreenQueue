"""
config.py — Central configuration with easy mock/real toggle.

Switch DATA_SOURCE between "mock" and "real":
  - "mock"  → uses deterministic sine-wave data (original behaviour)
  - "real"  → uses EIA/NASA data stored in eia_readings / nasa_readings tables
                + live hourly EIA API polling

You can override via the GREENQUEUE_DATA_SOURCE environment variable
or set it in backend/.env:
    GREENQUEUE_DATA_SOURCE=real python server.py
"""

import os
from dotenv import load_dotenv

# Load .env from backend/ directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ─── Data source toggle ────────────────────────────────
DATA_SOURCE: str = os.getenv("GREENQUEUE_DATA_SOURCE", "mock")  # "mock" | "real"

# ─── API keys ──────────────────────────────────────────
EIA_API_KEY: str = os.getenv("EIA_API_KEY", "")

# ─── Zone mapping ──────────────────────────────────────
MOCK_ZONE = "US-CAL-CISO"
REAL_ZONE = "US-MISO"

# EIA respondent ID corresponding to the zone
EIA_RESPONDENT = "MISO"

# Emission factors (gCO2 per MWh)
EMISSION_FACTORS = {
    "COL": 900,   # coal
    "NG":  400,   # natural gas
    "OIL": 700,   # oil/petroleum
}

def get_zone() -> str:
    """Return the active grid zone based on data source."""
    return REAL_ZONE if DATA_SOURCE == "real" else MOCK_ZONE
