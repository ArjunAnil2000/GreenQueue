"""
gcp_regions.py — Mapping of GCP Cloud regions to US grid balancing authorities.

Each GCP data-center sits within a specific electrical grid zone managed by
a balancing authority (BA).  The EIA API reports real-time generation data
keyed by BA respondent ID, so we can compare live carbon intensity across
the regions where Google Cloud actually runs workloads.

Reference: https://cloud.google.com/about/locations
"""

from config import EIA_RESPONDENT  # current active zone, e.g. "MISO"

# ── GCP Region → Grid Zone mapping ────────────────────────────────────────
# Each entry:
#   gcp_region  — official GCP region name
#   label       — human-friendly location label
#   respondent  — EIA balancing-authority code (used in API facets)
#   eia_zone    — zone string stored in our DB (US-{respondent})

GCP_REGION_MAP: list[dict] = [
    {
        "gcp_region": "us-central1",
        "label": "Iowa (Council Bluffs)",
        "respondent": "MISO",
        "eia_zone": "US-MISO",
    },
    {
        "gcp_region": "us-east4",
        "label": "Virginia (Ashburn)",
        "respondent": "PJM",
        "eia_zone": "US-PJM",
    },
    {
        "gcp_region": "us-south1",
        "label": "Texas (Dallas)",
        "respondent": "ERCO",
        "eia_zone": "US-ERCO",
    },
    {
        "gcp_region": "us-west1",
        "label": "Oregon (The Dalles)",
        "respondent": "BPAT",
        "eia_zone": "US-BPAT",
    },
    {
        "gcp_region": "us-west2",
        "label": "California (Los Angeles)",
        "respondent": "CISO",
        "eia_zone": "US-CISO",
    },
    {
        "gcp_region": "us-east1",
        "label": "S. Carolina (Moncks Corner)",
        "respondent": "DUK",
        "eia_zone": "US-DUK",
    },
    {
        "gcp_region": "us-east5",
        "label": "Ohio (Columbus)",
        "respondent": "PJM",
        "eia_zone": "US-PJM",
    },
    {
        "gcp_region": "us-west4",
        "label": "Nevada (Las Vegas)",
        "respondent": "NEVP",
        "eia_zone": "US-NEVP",
    },
]

# De-duplicate by respondent (PJM appears twice) for API calls
_seen = set()
UNIQUE_RESPONDENTS: list[dict] = []
for r in GCP_REGION_MAP:
    if r["respondent"] not in _seen:
        UNIQUE_RESPONDENTS.append(r)
        _seen.add(r["respondent"])


def get_active_respondent() -> str:
    """Return the BA respondent code for the currently active zone."""
    return EIA_RESPONDENT
