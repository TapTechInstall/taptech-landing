#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  TapTech Lead Qualification Engine v1.0
#  Find, score, and rank local business prospects.
#
#  Usage:
#    python lead_finder.py "Riverside, CA"
#    python lead_finder.py "92501"
#    python lead_finder.py "Corona, CA" --radius 15000
#    python lead_finder.py --batch        (scan all IE cities)
# ─────────────────────────────────────────────
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import requests

from config import (
    GOOGLE_PLACES_API_KEY,
    INDUSTRY_CONFIG,
    SEARCH_TERMS,
    IE_CITIES_PRIORITY,
    IE_CITIES_EXPANSION,
    DEFAULT_SEARCH_RADIUS,
)
from franchise_blocklist import is_franchise, get_matched_franchise
from scoring import score_business, generate_action


# ── ANSI Colors ─────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREEN   = "\033[38;2;0;229;160m"
    BLUE    = "\033[38;2;0;184;255m"
    RED     = "\033[38;2;255;77;106m"
    YELLOW  = "\033[38;2;255;214;0m"
    WHITE   = "\033[38;2;232;232;239m"
    GRAY    = "\033[38;2;136;136;160m"
    BG_DARK = "\033[48;2;18;18;26m"

    @staticmethod
    def tier_color(tier: str) -> str:
        return {
            "HOT": C.GREEN,
            "WARM": C.BLUE,
            "MAYBE": C.YELLOW,
            "SKIP": C.RED,
        }.get(tier, C.GRAY)


def print_banner():
    print(f"""
{C.GREEN}{C.BOLD}╔══════════════════════════════════════════════╗
║  TapTech Lead Qualification Engine  v1.0     ║
╚══════════════════════════════════════════════╝{C.RESET}
""")


def print_progress(msg: str, end="\n"):
    print(f"  {C.GRAY}→{C.RESET} {msg}", end=end, flush=True)


def print_stat(label: str, value, color=C.GREEN):
    print(f"  {C.GRAY}{label}:{C.RESET} {color}{C.BOLD}{value}{C.RESET}")


# ── Google Places API (New) ─────────────────
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.types",
])


def search_places(query: str, api_key: str, max_pages: int = 1) -> list[dict]:
    """
    Search Google Places API (New) with a text query.
    Returns a list of place dicts.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    body = {
        "textQuery": query,
        "maxResultCount": 20,
        "languageCode": "en",
    }

    all_places = []
    page = 0

    while page < max_pages:
        try:
            resp = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=15)

            if resp.status_code == 429:
                print_progress(f"{C.YELLOW}Rate limited, waiting 5s...{C.RESET}")
                time.sleep(5)
                continue

            if resp.status_code != 200:
                print_progress(f"{C.RED}API error {resp.status_code}: {resp.text[:200]}{C.RESET}")
                break

            data = resp.json()
            places = data.get("places", [])
            all_places.extend(places)

            # Check for next page
            next_token = data.get("nextPageToken")
            if next_token and page + 1 < max_pages:
                body["pageToken"] = next_token
                time.sleep(1.5)  # Required delay for pagination
                page += 1
            else:
                break

        except requests.exceptions.RequestException as e:
            print_progress(f"{C.RED}Network error: {e}{C.RESET}")
            break

    return all_places


def parse_place(place: dict, search_term: str) -> dict | None:
    """
    Parse a Google Places API result into our lead data model.
    Returns None if the business should be skipped.
    """
    name = place.get("displayName", {}).get("text", "Unknown")
    address = place.get("formattedAddress", "")
    status = place.get("businessStatus", "")

    # Skip permanently closed
    if status == "CLOSED_PERMANENTLY":
        return None

    review_count = place.get("userRatingCount")
    rating = place.get("rating")
    website = place.get("websiteUri", "")
    phone = place.get("nationalPhoneNumber", "") or place.get("internationalPhoneNumber", "")
    maps_url = place.get("googleMapsUri", "")
    place_id = place.get("id", "")

    # ── Disqualifier: 500+ reviews ──
    if review_count and review_count >= 500:
        return None

    # ── Chain detection ──
    chain = is_franchise(name)
    matched_chain = get_matched_franchise(name) if chain else None

    # ── Scoring ──
    industry_cfg = INDUSTRY_CONFIG.get(search_term, {"tier": "C", "points": 10})
    industry_points = industry_cfg["points"]
    industry_tier = industry_cfg["tier"]

    result = score_business(
        industry_points=industry_points,
        review_count=review_count,
        rating=rating,
        website=website,
        is_chain=chain,
    )

    # ── Determine digital presence label ──
    if not website:
        digital_label = "none"
    elif any(d in website.lower() for d in ["facebook.com", "instagram.com", "yelp.com", "linkedin.com"]):
        digital_label = "social_only"
    elif any(d in website.lower() for d in ["wix.com", "weebly.com", "squarespace.com", "wordpress.com", "carrd.co", "linktr.ee"]):
        digital_label = "basic"
    else:
        digital_label = "professional"

    action = generate_action(
        name=name,
        tier=result.tier,
        industry=search_term,
        review_count=review_count,
        website=website,
        rating=rating,
    )

    return {
        "business_name": name,
        "industry": search_term,
        "industry_tier": industry_tier,
        "address": address,
        "city": extract_city(address),
        "phone": phone,
        "website": website or "none",
        "google_maps_url": maps_url,
        "google_rating": rating,
        "google_review_count": review_count or 0,
        "is_chain": chain,
        "matched_chain": matched_chain or "",
        "digital_presence": digital_label,
        "place_id": place_id,

        # Scores
        "fit_score": result.total,
        "score_industry": result.industry_match,
        "score_reviews": result.review_gap,
        "score_rating": result.rating_gap,
        "score_digital": result.digital_presence,
        "score_independence": result.independence,
        "lead_tier": result.tier,
        "recommended_action": action,

        # Tracking (user fills in later)
        "status": "not_contacted",
        "contact_date": "",
        "notes": "",
    }


def extract_city(address: str) -> str:
    """Try to pull city from formatted address like '123 Main St, Riverside, CA 92501'."""
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return parts[-2].split()[0] if parts[-2].strip() else parts[1]
    elif len(parts) == 2:
        return parts[0]
    return ""


def deduplicate(leads: list[dict]) -> list[dict]:
    """Remove duplicate businesses by place_id or name+address."""
    seen = set()
    unique = []
    for lead in leads:
        key = lead.get("place_id") or f"{lead['business_name']}|{lead['address']}"
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


def export_csv(leads: list[dict], filename: str):
    """Export leads to CSV file."""
    if not leads:
        print_progress(f"{C.YELLOW}No leads to export.{C.RESET}")
        return

    fieldnames = [
        "fit_score", "lead_tier", "business_name", "industry", "industry_tier",
        "address", "city", "phone", "website", "google_maps_url",
        "google_rating", "google_review_count", "is_chain", "digital_presence",
        "score_industry", "score_reviews", "score_rating", "score_digital",
        "score_independence", "recommended_action",
        "status", "contact_date", "notes",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)

    print_progress(f"Exported to {C.GREEN}{C.BOLD}{filename}{C.RESET}")


def print_results_table(leads: list[dict], max_rows: int = 30):
    """Print a formatted results table to the terminal."""
    if not leads:
        print(f"\n  {C.YELLOW}No leads found.{C.RESET}\n")
        return

    print(f"\n  {C.GREEN}{C.BOLD}{'SCORE':<7} {'TIER':<7} {'BUSINESS':<32} {'INDUSTRY':<20} {'REV':<6} {'RAT':<6} {'WEB':<10} {'ACTION'}{C.RESET}")
    print(f"  {C.GRAY}{'─' * 120}{C.RESET}")

    for lead in leads[:max_rows]:
        tc = C.tier_color(lead["lead_tier"])
        score = lead["fit_score"]
        tier = lead["lead_tier"]
        name = lead["business_name"][:30]
        ind = lead["industry"][:18]
        rev = lead["google_review_count"]
        rat = lead["google_rating"] or "N/A"
        web = lead["digital_presence"][:8]
        action = lead["recommended_action"][:50]

        print(
            f"  {tc}{C.BOLD}{score:<7}{C.RESET}"
            f" {tc}{tier:<7}{C.RESET}"
            f" {C.WHITE}{name:<32}{C.RESET}"
            f" {C.GRAY}{ind:<20}{C.RESET}"
            f" {C.GRAY}{rev:<6}{C.RESET}"
            f" {C.GRAY}{rat:<6}{C.RESET}"
            f" {C.GRAY}{web:<10}{C.RESET}"
            f" {C.DIM}{action}{C.RESET}"
        )

    if len(leads) > max_rows:
        print(f"\n  {C.GRAY}... and {len(leads) - max_rows} more (see CSV){C.RESET}")


def print_summary(leads: list[dict], filtered_chains: int, filtered_reviews: int):
    """Print summary statistics."""
    hot = sum(1 for l in leads if l["lead_tier"] == "HOT")
    warm = sum(1 for l in leads if l["lead_tier"] == "WARM")
    maybe = sum(1 for l in leads if l["lead_tier"] == "MAYBE")
    skip = sum(1 for l in leads if l["lead_tier"] == "SKIP")
    avg_score = sum(l["fit_score"] for l in leads) / len(leads) if leads else 0

    print(f"\n{C.GREEN}{C.BOLD}  ── Summary ──{C.RESET}")
    print_stat("Total leads scored", len(leads))
    print_stat("Chains filtered out", filtered_chains, C.RED)
    print_stat("500+ review filtered", filtered_reviews, C.RED)
    print_stat("Average fit score", f"{avg_score:.0f}")
    print()
    print_stat("🔥 HOT leads (80+)", hot, C.GREEN)
    print_stat("🟡 WARM leads (60-79)", warm, C.BLUE)
    print_stat("🔵 MAYBE (40-59)", maybe, C.YELLOW)
    print_stat("⚫ SKIP (<40)", skip, C.RED)


def run_search(location: str, radius: int = DEFAULT_SEARCH_RADIUS, search_terms: list[str] | None = None):
    """
    Main search pipeline.
    1. Search each industry keyword in the location
    2. Filter chains and disqualified businesses
    3. Score and rank
    4. Return sorted leads + stats
    """
    terms = search_terms or SEARCH_TERMS
    all_leads = []
    total_raw = 0
    filtered_chains = 0
    filtered_reviews = 0

    print(f"\n  {C.GREEN}{C.BOLD}Scanning:{C.RESET} {C.WHITE}{location}{C.RESET}")
    print(f"  {C.GRAY}Industries: {len(terms)} · Radius: {radius}m{C.RESET}\n")

    for i, term in enumerate(terms, 1):
        query = f"{term} in {location}"
        tier = INDUSTRY_CONFIG.get(term, {}).get("tier", "?")
        progress_pct = f"[{i}/{len(terms)}]"

        print_progress(
            f"{C.GRAY}{progress_pct}{C.RESET} "
            f"Searching {C.WHITE}{term}{C.RESET} "
            f"{C.GRAY}(Tier {tier}){C.RESET}",
            end=""
        )

        places = search_places(query, GOOGLE_PLACES_API_KEY)

        found = 0
        chains = 0
        high_reviews = 0

        for place in places:
            total_raw += 1
            parsed = parse_place(place, term)

            if parsed is None:
                # Check why it was skipped
                name = place.get("displayName", {}).get("text", "")
                count = place.get("userRatingCount", 0)
                if count and count >= 500:
                    high_reviews += 1
                    filtered_reviews += 1
                continue

            if parsed["is_chain"]:
                chains += 1
                filtered_chains += 1
                continue

            all_leads.append(parsed)
            found += 1

        status_parts = [f"{C.GREEN}{found} leads{C.RESET}"]
        if chains:
            status_parts.append(f"{C.RED}{chains} chains{C.RESET}")
        if high_reviews:
            status_parts.append(f"{C.YELLOW}{high_reviews} high-rev{C.RESET}")

        print(f" → {', '.join(status_parts)}")

        # Small delay between searches to be nice to the API
        if i < len(terms):
            time.sleep(0.5)

    # Deduplicate
    before_dedup = len(all_leads)
    all_leads = deduplicate(all_leads)
    dupes_removed = before_dedup - len(all_leads)
    if dupes_removed:
        print_progress(f"Removed {C.YELLOW}{dupes_removed}{C.RESET} duplicates")

    # Sort by score descending
    all_leads.sort(key=lambda x: x["fit_score"], reverse=True)

    return all_leads, filtered_chains, filtered_reviews


def main():
    parser = argparse.ArgumentParser(
        description="TapTech Lead Qualification Engine — Find and score local business prospects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python lead_finder.py "Riverside, CA"
  python lead_finder.py "92501" --radius 15000
  python lead_finder.py --batch
  python lead_finder.py "Corona, CA" --industries "barbershop,tattoo shop,nail salon"
  python lead_finder.py "Fontana, CA" --output my_leads.csv
        """,
    )

    parser.add_argument("location", nargs="?", help="City, zip code, or neighborhood to search")
    parser.add_argument("--radius", type=int, default=DEFAULT_SEARCH_RADIUS, help=f"Search radius in meters (default: {DEFAULT_SEARCH_RADIUS})")
    parser.add_argument("--output", "-o", type=str, help="Output CSV filename (default: auto-generated)")
    parser.add_argument("--industries", type=str, help="Comma-separated list of industries to search (default: all)")
    parser.add_argument("--batch", action="store_true", help="Scan all priority Inland Empire cities")
    parser.add_argument("--batch-all", action="store_true", help="Scan ALL Inland Empire cities (priority + expansion)")
    parser.add_argument("--min-score", type=int, default=0, help="Only include leads with score >= this value")
    parser.add_argument("--json", action="store_true", help="Also export as JSON")

    args = parser.parse_args()

    # ── Validate API key ──
    if not GOOGLE_PLACES_API_KEY:
        print(f"\n  {C.RED}{C.BOLD}ERROR:{C.RESET} No Google Places API key found.")
        print(f"  {C.GRAY}Create a .env file with:{C.RESET}")
        print(f"  {C.GREEN}GOOGLE_PLACES_API_KEY=your_key_here{C.RESET}\n")
        print(f"  {C.GRAY}Get a key at: https://console.cloud.google.com/apis/credentials{C.RESET}")
        print(f"  {C.GRAY}Enable 'Places API (New)' in your Google Cloud project.{C.RESET}\n")
        sys.exit(1)

    # ── Determine locations to scan ──
    if args.batch or args.batch_all:
        locations = [f"{city}, CA" for city in IE_CITIES_PRIORITY]
        if args.batch_all:
            locations += [f"{city}, CA" for city in IE_CITIES_EXPANSION]
    elif args.location:
        locations = [args.location]
    else:
        parser.print_help()
        sys.exit(1)

    # ── Determine industries ──
    search_terms = None
    if args.industries:
        search_terms = [t.strip() for t in args.industries.split(",")]
        # Validate
        for t in search_terms:
            if t not in INDUSTRY_CONFIG:
                print(f"  {C.YELLOW}Warning: '{t}' not in industry config. Using default 10 pts.{C.RESET}")

    print_banner()

    # ── Run searches ──
    all_leads = []
    total_chains = 0
    total_high_rev = 0

    for location in locations:
        leads, chains, high_rev = run_search(location, args.radius, search_terms)
        all_leads.extend(leads)
        total_chains += chains
        total_high_rev += high_rev

    # Deduplicate across cities (for batch mode)
    if len(locations) > 1:
        before = len(all_leads)
        all_leads = deduplicate(all_leads)
        cross_dupes = before - len(all_leads)
        if cross_dupes:
            print_progress(f"Removed {C.YELLOW}{cross_dupes}{C.RESET} cross-city duplicates")

    # Sort all leads
    all_leads.sort(key=lambda x: x["fit_score"], reverse=True)

    # Apply min score filter
    if args.min_score > 0:
        before = len(all_leads)
        all_leads = [l for l in all_leads if l["fit_score"] >= args.min_score]
        print_progress(f"Filtered to {len(all_leads)} leads with score >= {args.min_score} (removed {before - len(all_leads)})")

    # ── Output ──
    print_results_table(all_leads)
    print_summary(all_leads, total_chains, total_high_rev)

    # Generate filename
    if args.output:
        csv_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.batch or args.batch_all:
            csv_file = f"leads_IE_{timestamp}.csv"
        else:
            safe_loc = args.location.replace(",", "").replace(" ", "_").lower()
            csv_file = f"leads_{safe_loc}_{timestamp}.csv"

    print()
    export_csv(all_leads, csv_file)

    # Optional JSON export
    if args.json:
        json_file = csv_file.replace(".csv", ".json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_leads, f, indent=2, ensure_ascii=False)
        print_progress(f"Exported to {C.GREEN}{C.BOLD}{json_file}{C.RESET}")

    # Final message
    hot_count = sum(1 for l in all_leads if l["lead_tier"] == "HOT")
    if hot_count:
        print(f"\n  {C.GREEN}{C.BOLD}🔥 {hot_count} HOT leads ready for outreach!{C.RESET}\n")
    else:
        print(f"\n  {C.GRAY}No HOT leads found. Try expanding the search area or industries.{C.RESET}\n")


if __name__ == "__main__":
    main()
