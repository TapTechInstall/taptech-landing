# ─────────────────────────────────────────────
#  TapTech Lead Engine — Franchise Blocklist
#  Businesses matching these names are filtered out.
#  Uses substring matching (case-insensitive).
# ─────────────────────────────────────────────
from __future__ import annotations
import re

FRANCHISE_NAMES = frozenset([
    # ── Insurance (corporate offices) ──
    "state farm", "allstate", "farmers insurance", "geico", "progressive",
    "liberty mutual", "nationwide", "american family", "the hartford",
    "erie insurance", "shelter insurance", "country financial",

    # ── Real estate (corporate brands) ──
    "keller williams", "re/max", "remax", "coldwell banker", "century 21",
    "sotheby's", "berkshire hathaway", "compass real estate", "redfin",
    "exp realty", "weichert", "howard hanna",

    # ── Fitness chains ──
    "planet fitness", "la fitness", "24 hour fitness", "gold's gym",
    "golds gym", "anytime fitness", "orangetheory", "orange theory",
    "crunch fitness", "equinox", "lifetime fitness", "life time fitness",
    "snap fitness", "retro fitness", "eos fitness", "blink fitness",
    "f45 training", "crossfit",  # note: some crossfit are independent

    # ── Hair / beauty chains ──
    "great clips", "supercuts", "sport clips", "fantastic sams",
    "cost cutters", "smartstyle", "mastercuts", "hair cuttery",
    "ulta beauty", "sephora", "european wax center", "waxing the city",
    "drybar", "regis salon", "visible changes",

    # ── Nail salon chains ──
    "regal nails", "polished nail bar",

    # ── Car dealership groups ──
    "autonation", "penske automotive", "hendrick automotive",
    "larry h. miller", "sonic automotive", "group 1 automotive",
    "lithia motors", "carvana", "carmax", "vroom",

    # ── Solar chains ──
    "sunrun", "vivint solar", "tesla solar", "sunpower", "sunnova",
    "freedom solar", "palmetto solar", "blue raven solar",

    # ── Photography chains ──
    "jcpenney portraits", "picture people", "lifetouch",
    "shutterfly", "olan mills",

    # ── Financial chains ──
    "edward jones", "ameriprise", "raymond james", "merrill lynch",
    "morgan stanley", "charles schwab", "fidelity", "wells fargo",
    "bank of america", "chase bank", "td ameritrade",
    "northwestern mutual", "primerica", "transamerica",
    "new york life", "mass mutual", "massmutual", "prudential",

    # ── Mortgage chains ──
    "quicken loans", "rocket mortgage", "loanDepot", "loandepot",
    "caliber home loans", "guild mortgage", "pennymac",
    "united wholesale mortgage", "better.com",

    # ── Yoga / wellness chains ──
    "corepower yoga", "hot yoga", "bikram yoga",  # many bikrams are chains
    "yoga works", "yogaworks",

    # ── Misc ──
    "h&r block", "jackson hewitt", "liberty tax",
    "the ups store", "fedex office",
    "massage envy", "hand and stone", "elements massage",
])


def normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"[''`]", "'", name)    # normalize apostrophes
    name = re.sub(r"[^\w\s'/&-]", "", name)  # keep letters, digits, basic punctuation
    name = re.sub(r"\s+", " ", name)
    return name


def is_franchise(business_name: str) -> bool:
    """
    Check if a business name matches any known franchise.
    Uses substring matching so "State Farm - John Rivera" still matches.
    """
    normalized = normalize(business_name)
    for franchise in FRANCHISE_NAMES:
        if franchise in normalized:
            return True
    return False


def get_matched_franchise(business_name: str) -> str | None:
    """Return the matched franchise name, or None."""
    normalized = normalize(business_name)
    for franchise in FRANCHISE_NAMES:
        if franchise in normalized:
            return franchise
    return None
