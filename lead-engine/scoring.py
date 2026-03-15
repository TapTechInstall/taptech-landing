# ─────────────────────────────────────────────
#  TapTech Lead Engine — Scoring Model
#  Scores businesses 0–100 on TapTech fit.
# ─────────────────────────────────────────────
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ScoreResult:
    """Breakdown of a business's TapTech Fit Score."""
    industry_match: int    # 0–25
    review_gap: int        # 0–25
    rating_gap: int        # 0–15
    digital_presence: int  # 0–20
    independence: int      # 0–15

    @property
    def total(self) -> int:
        return (
            self.industry_match
            + self.review_gap
            + self.rating_gap
            + self.digital_presence
            + self.independence
        )

    @property
    def tier(self) -> str:
        t = self.total
        if t >= 80:
            return "HOT"
        elif t >= 60:
            return "WARM"
        elif t >= 40:
            return "MAYBE"
        else:
            return "SKIP"

    @property
    def tier_emoji(self) -> str:
        return {"HOT": "🔥", "WARM": "🟡", "MAYBE": "🔵", "SKIP": "⚫"}[self.tier]

    def breakdown_str(self) -> str:
        return (
            f"IND:{self.industry_match} "
            f"REV:{self.review_gap} "
            f"RAT:{self.rating_gap} "
            f"DIG:{self.digital_presence} "
            f"IDP:{self.independence}"
        )


def score_industry(industry_points: int) -> int:
    """
    Industry match score (0–25).
    Points come directly from config.INDUSTRY_CONFIG.
    """
    return max(0, min(25, industry_points))


def score_review_gap(review_count: int) -> int:
    """
    Google review gap score (0–25).
    Fewer reviews = more room to grow = higher score.
    """
    if review_count is None:
        return 25  # No reviews at all = maximum opportunity
    if review_count <= 10:
        return 25
    elif review_count <= 50:
        return 20
    elif review_count <= 100:
        return 12
    elif review_count <= 250:
        return 5
    else:
        return 0


def score_rating_gap(rating: float) -> int:
    """
    Google rating gap score (0–15).
    Lower rating = needs more help = higher score.
    """
    if rating is None:
        return 15  # No rating = maximum opportunity
    if rating < 4.0:
        return 15
    elif rating < 4.3:
        return 12
    elif rating < 4.6:
        return 8
    else:
        return 4


def score_digital_presence(website: str | None) -> int:
    """
    Digital presence score (0–20).
    No website = needs TapTech the most.

    In v1 we do binary: has website or doesn't.
    Future versions can check website quality.
    """
    if not website or website.strip() == "":
        return 20  # No website at all

    # Basic heuristics for website quality
    w = website.lower()

    # Social-media-only "websites" count as basic
    social_domains = ["facebook.com", "instagram.com", "yelp.com", "linkedin.com"]
    if any(domain in w for domain in social_domains):
        return 16  # Social media only, no real website

    # Free website builders = basic
    basic_domains = [
        "wix.com", "weebly.com", "squarespace.com", "godaddy.com",
        "wordpress.com", "sites.google.com", "carrd.co", "linktree",
        "linktr.ee", "bio.link",
    ]
    if any(domain in w for domain in basic_domains):
        return 14  # Basic/free website

    # Has a real website — give some credit but still a prospect
    return 6


def score_independence(is_chain: bool) -> int:
    """
    Independence score (0–15).
    Independent businesses can make buying decisions on the spot.
    """
    if is_chain:
        return 0
    return 15


def score_business(
    industry_points: int,
    review_count: int | None,
    rating: float | None,
    website: str | None,
    is_chain: bool,
) -> ScoreResult:
    """
    Calculate the full TapTech Fit Score for a business.
    Returns a ScoreResult with breakdown and total.
    """
    return ScoreResult(
        industry_match=score_industry(industry_points),
        review_gap=score_review_gap(review_count),
        rating_gap=score_rating_gap(rating),
        digital_presence=score_digital_presence(website),
        independence=score_independence(is_chain),
    )


def generate_action(
    name: str,
    tier: str,
    industry: str,
    review_count: int | None,
    website: str | None,
    rating: float | None,
) -> str:
    """Generate a recommended action string for the lead."""
    reviews = review_count or 0
    has_site = bool(website and website.strip())

    if tier == "HOT":
        parts = []
        if not has_site:
            parts.append("no website")
        if reviews <= 10:
            parts.append(f"only {reviews} reviews")
        elif reviews <= 50:
            parts.append(f"{reviews} reviews, room to grow")
        detail = ", ".join(parts) if parts else "strong TapTech fit"
        return f"Walk in — {detail}. Demo the card."

    elif tier == "WARM":
        if has_site and reviews > 50:
            return f"Email — decent reviews ({reviews}) but could use tap card for networking."
        elif has_site:
            return f"Email — has basic web presence, {reviews} reviews. Pitch Google growth."
        else:
            return f"Walk in or email — {reviews} reviews, no website. Good candidate."

    elif tier == "MAYBE":
        return "Skip unless nearby or you have a connection."

    else:
        reasons = []
        if review_count and review_count > 250:
            reasons.append(f"{review_count} reviews already")
        if has_site:
            reasons.append("has web presence")
        return "Skip — " + (", ".join(reasons) if reasons else "low fit score") + "."
