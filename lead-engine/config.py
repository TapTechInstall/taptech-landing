# ─────────────────────────────────────────────
#  TapTech Lead Engine — Configuration
# ─────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

# ── Industry tiers ──────────────────────────
# Tier A = high-networking, personal brand professions (25 pts)
# Tier B = service businesses with moderate networking (18 pts)
# Tier C = professional services, less networking (10 pts)

INDUSTRY_CONFIG = {
    # ── TIER A (25 pts) ──
    "real estate agent":     {"tier": "A", "points": 25},
    "barbershop":            {"tier": "A", "points": 25},
    "hair salon":            {"tier": "A", "points": 25},
    "personal trainer":      {"tier": "A", "points": 25},
    "tattoo shop":           {"tier": "A", "points": 25},
    "DJ services":           {"tier": "A", "points": 25},
    "photographer":          {"tier": "A", "points": 25},
    "makeup artist":         {"tier": "A", "points": 25},
    "car dealership":        {"tier": "A", "points": 25},
    "nail salon":            {"tier": "A", "points": 25},

    # ── TIER B (18 pts) ──
    "insurance agent":       {"tier": "B", "points": 18},
    "solar installer":       {"tier": "B", "points": 18},
    "yoga studio":           {"tier": "B", "points": 18},
    "gym personal training": {"tier": "B", "points": 18},
    "videographer":          {"tier": "B", "points": 18},
    "boxing gym":            {"tier": "B", "points": 18},
    "music producer":        {"tier": "B", "points": 18},

    # ── TIER C (10 pts) ──
    "graphic designer":      {"tier": "C", "points": 10},
    "mortgage broker":       {"tier": "C", "points": 10},
    "financial advisor":     {"tier": "C", "points": 10},
}

# All search terms in order
SEARCH_TERMS = list(INDUSTRY_CONFIG.keys())

# ── Inland Empire cities ────────────────────
# Green = priority (closest, highest density)
# Blue  = expansion targets
IE_CITIES_PRIORITY = [
    "Riverside", "Corona", "Moreno Valley", "Fontana",
    "Rancho Cucamonga", "Ontario", "San Bernardino",
    "Temecula", "Murrieta", "Redlands",
]

IE_CITIES_EXPANSION = [
    "Perris", "Lake Elsinore", "Eastvale", "Jurupa Valley",
    "Menifee", "Beaumont", "Hemet", "Upland", "Chino", "Chino Hills",
]

# ── API settings ────────────────────────────
DEFAULT_SEARCH_RADIUS = 10000  # meters (≈6 miles)
MAX_RESULTS_PER_SEARCH = 20    # Google Places returns max 20 per page
