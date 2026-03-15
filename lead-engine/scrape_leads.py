#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  TapTech Lead Scraper — Google Maps
#  Scrapes business data from Google Maps search.
#  No API key needed. Outputs CSV for dashboard import.
#
#  Usage:
#    python scrape_leads.py "Riverside, CA"
#    python scrape_leads.py "Corona, CA" --industries "barbershop,tattoo shop"
#    python scrape_leads.py --batch
#    python scrape_leads.py "92501" --max-per-industry 30
# ─────────────────────────────────────────────
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
import random
from datetime import datetime
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── ANSI Colors ──
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


# ── Industry config (matches dashboard) ──
INDUSTRY_CONFIG = {
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
    "insurance agent":       {"tier": "B", "points": 18},
    "solar installer":       {"tier": "B", "points": 18},
    "yoga studio":           {"tier": "B", "points": 18},
    "gym personal training": {"tier": "B", "points": 18},
    "videographer":          {"tier": "B", "points": 18},
    "boxing gym":            {"tier": "B", "points": 18},
    "music producer":        {"tier": "B", "points": 18},
    "graphic designer":      {"tier": "C", "points": 10},
    "mortgage broker":       {"tier": "C", "points": 10},
    "financial advisor":     {"tier": "C", "points": 10},
}

ALL_INDUSTRIES = list(INDUSTRY_CONFIG.keys())

IE_CITIES_PRIORITY = [
    "Riverside, CA", "Corona, CA", "Moreno Valley, CA", "Fontana, CA",
    "Rancho Cucamonga, CA", "Ontario, CA", "San Bernardino, CA",
    "Temecula, CA", "Murrieta, CA", "Redlands, CA",
]

# ── Franchise blocklist (subset for quick check) ──
FRANCHISE_WORDS = {
    "state farm", "allstate", "farmers insurance", "geico", "progressive",
    "liberty mutual", "nationwide", "keller williams", "re/max", "remax",
    "coldwell banker", "century 21", "berkshire hathaway", "compass",
    "planet fitness", "la fitness", "24 hour fitness", "gold's gym",
    "anytime fitness", "orangetheory", "crunch fitness", "equinox",
    "snap fitness", "f45 training", "great clips", "supercuts",
    "sport clips", "fantastic sams", "cost cutters", "hair cuttery",
    "european wax center", "ulta beauty", "sephora",
    "autonation", "carmax", "carvana", "penske",
    "sunrun", "vivint solar", "tesla solar", "sunpower",
    "edward jones", "ameriprise", "merrill lynch", "morgan stanley",
    "charles schwab", "fidelity", "wells fargo", "northwestern mutual",
    "primerica", "quicken loans", "rocket mortgage",
    "massage envy", "hand and stone", "corepower yoga",
    "h&r block", "jackson hewitt", "liberty tax",
    "lifetouch", "jcpenney portraits",
}

def is_franchise(name):
    n = name.lower().strip()
    for f in FRANCHISE_WORDS:
        if f in n:
            return True
    return False


def print_banner():
    print(f"""
{C.GREEN}{C.BOLD}╔══════════════════════════════════════════════╗
║  TapTech Lead Scraper — Google Maps          ║
║  No API key needed · Free · Unlimited        ║
╚══════════════════════════════════════════════╝{C.RESET}
""")


def print_progress(msg, end="\n"):
    print(f"  {C.GRAY}→{C.RESET} {msg}", end=end, flush=True)


def extract_number(text):
    """Pull a number from text like '(123)' or '4.5'."""
    if not text:
        return None
    nums = re.findall(r'[\d,.]+', text.replace(',', ''))
    return nums[0] if nums else None


def scrape_google_maps(page, query, industry, max_results=20):
    """
    Scrape Google Maps search results for a query.
    Returns list of business dicts, already scored.
    """
    businesses = []
    seen_names = set()

    url = f"https://www.google.com/maps/search/{quote_plus(query)}"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

        # Accept cookies if prompted (EU/etc)
        try:
            accept_btn = page.locator('button:has-text("Accept all")')
            if accept_btn.is_visible(timeout=2000):
                accept_btn.click()
                time.sleep(1)
        except:
            pass

        # Wait for results feed to appear
        feed_selector = 'div[role="feed"]'
        try:
            page.wait_for_selector(feed_selector, timeout=10000)
        except PWTimeout:
            # Try alternate layout - single result or list view
            pass

        # Scroll the results panel to load more
        feed = page.locator(feed_selector).first
        if feed.is_visible():
            prev_count = 0
            scroll_attempts = 0
            max_scrolls = 8  # limit scrolling

            while scroll_attempts < max_scrolls:
                # Count current results
                items = page.locator(f'{feed_selector} > div > div > a[href*="/maps/place/"]').all()
                current_count = len(items)

                if current_count >= max_results:
                    break
                if current_count == prev_count:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0

                prev_count = current_count

                # Scroll down
                feed.evaluate('el => el.scrollTop = el.scrollHeight')
                time.sleep(1.5 + random.random())

        # Now extract all result links
        result_links = page.locator('a[href*="/maps/place/"]').all()

        for i, link in enumerate(result_links):
            if len(businesses) >= max_results:
                break

            try:
                # Extract basic info from the card
                aria_label = link.get_attribute("aria-label") or ""
                href = link.get_attribute("href") or ""

                if not aria_label or aria_label in seen_names:
                    continue
                seen_names.add(aria_label)

                name = aria_label.strip()

                # Skip franchises
                if is_franchise(name):
                    print_progress(f"{C.RED}✕ Franchise: {name}{C.RESET}")
                    continue

                # Click into the listing to get details
                try:
                    link.click(timeout=5000)
                    time.sleep(2 + random.random() * 0.5)
                except:
                    continue

                biz = extract_place_details(page, name, href)
                if biz:
                    # Skip 500+ reviews
                    if biz.get("google_review_count", 0) >= 500:
                        print_progress(f"{C.YELLOW}✕ 500+ reviews: {name} ({biz['google_review_count']}){C.RESET}")
                        continue

                    # Score it immediately
                    biz = score_lead(biz, industry)
                    businesses.append(biz)
                    score = biz.get("fit_score", 0)
                    tier = biz.get("lead_tier", "?")
                    tc = C.GREEN if tier == "HOT" else C.BLUE if tier == "WARM" else C.YELLOW if tier == "MAYBE" else C.RED
                    rev = biz.get("google_review_count", 0)
                    web = "no site" if not biz.get("website") or biz["website"] == "none" else "has site"
                    print_progress(f"{tc}{score:>3} {tier:<5}{C.RESET} {C.WHITE}{name[:40]}{C.RESET} {C.GRAY}({rev} reviews · {web}){C.RESET}")

                # Go back to results (skip if we already have enough)
                if len(businesses) >= max_results:
                    break
                try:
                    page.go_back(wait_until="domcontentloaded", timeout=6000)
                    time.sleep(1)
                    page.wait_for_selector(feed_selector, timeout=6000)
                except:
                    # If back navigation fails, re-navigate
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        time.sleep(2)
                        page.wait_for_selector(feed_selector, timeout=6000)
                    except:
                        break

            except Exception as e:
                continue

    except Exception as e:
        print_progress(f"{C.RED}Error loading Maps: {e}{C.RESET}")

    return businesses


def extract_place_details(page, name, maps_url):
    """Extract detailed info from a Google Maps place page."""
    biz = {
        "business_name": name,
        "google_maps_url": maps_url,
        "address": "",
        "phone": "",
        "website": "",
        "google_rating": None,
        "google_review_count": 0,
    }

    try:
        # Wait for detail panel
        time.sleep(1)

        # ── Rating ──
        try:
            rating_el = page.locator('div.F7nice span[aria-hidden="true"]').first
            if rating_el.is_visible(timeout=2000):
                rating_text = rating_el.inner_text()
                try:
                    biz["google_rating"] = float(rating_text.strip())
                except:
                    pass
        except:
            pass

        # ── Review count ──
        try:
            review_el = page.locator('div.F7nice span[aria-label*="review"]').first
            if review_el.is_visible(timeout=1000):
                label = review_el.get_attribute("aria-label") or ""
                num = extract_number(label)
                if num:
                    biz["google_review_count"] = int(float(num))
        except:
            pass

        # ── Address, Phone, Website from info buttons ──
        try:
            # Address - button with data-item-id="address"
            addr_btn = page.locator('button[data-item-id="address"]')
            if addr_btn.count() > 0 and addr_btn.first.is_visible(timeout=1500):
                addr_text = addr_btn.first.get_attribute("aria-label") or ""
                biz["address"] = addr_text.replace("Address: ", "").strip()
        except:
            pass

        try:
            # Phone - button with data-item-id starting with "phone"
            phone_btn = page.locator('button[data-item-id^="phone"]')
            if phone_btn.count() > 0 and phone_btn.first.is_visible(timeout=1000):
                phone_text = phone_btn.first.get_attribute("aria-label") or ""
                biz["phone"] = phone_text.replace("Phone: ", "").strip()
        except:
            pass

        try:
            # Website - link with data-item-id="authority"
            web_link = page.locator('a[data-item-id="authority"]')
            if web_link.count() > 0 and web_link.first.is_visible(timeout=1000):
                href = web_link.first.get_attribute("href") or ""
                if href:
                    biz["website"] = href
        except:
            pass

        # ── Current Google Maps URL ──
        try:
            biz["google_maps_url"] = page.url
        except:
            pass

    except Exception as e:
        pass

    return biz


def score_lead(biz, industry):
    """Score a business using the TapTech scoring model."""
    cfg = INDUSTRY_CONFIG.get(industry, {"tier": "C", "points": 5})

    # Industry match (0-25)
    s_industry = cfg["points"]

    # Review gap (0-25)
    rev = biz.get("google_review_count", 0)
    if rev <= 10:
        s_reviews = 25
    elif rev <= 50:
        s_reviews = 20
    elif rev <= 100:
        s_reviews = 12
    elif rev <= 250:
        s_reviews = 5
    else:
        s_reviews = 0

    # Rating gap (0-15)
    rating = biz.get("google_rating")
    if rating is None:
        s_rating = 15
    elif rating < 4.0:
        s_rating = 15
    elif rating < 4.3:
        s_rating = 12
    elif rating < 4.6:
        s_rating = 8
    else:
        s_rating = 4

    # Digital presence (0-20)
    website = biz.get("website", "")
    if not website or website == "none":
        s_digital = 20
    elif any(d in website.lower() for d in ["facebook.com", "instagram.com", "yelp.com"]):
        s_digital = 16
    elif any(d in website.lower() for d in ["wix.com", "squarespace.com", "weebly.com", "wordpress.com", "linktr.ee"]):
        s_digital = 14
    else:
        s_digital = 6

    # Independence (0-15) - already filtered franchises
    s_independence = 15 if not is_franchise(biz["business_name"]) else 0

    total = s_industry + s_reviews + s_rating + s_digital + s_independence
    tier = "HOT" if total >= 80 else "WARM" if total >= 60 else "MAYBE" if total >= 40 else "SKIP"

    biz["industry"] = industry
    biz["industry_tier"] = cfg["tier"]
    biz["is_chain"] = False
    biz["fit_score"] = total
    biz["lead_tier"] = tier
    biz["score_industry"] = s_industry
    biz["score_reviews"] = s_reviews
    biz["score_rating"] = s_rating
    biz["score_digital"] = s_digital
    biz["score_independence"] = s_independence
    biz["status"] = "not_contacted"
    biz["contact_date"] = ""
    biz["notes"] = ""

    # City extraction
    addr = biz.get("address", "")
    parts = [p.strip() for p in addr.split(",")]
    biz["city"] = parts[-2].split()[0] if len(parts) >= 3 else ""

    # Action
    has_site = bool(website and website != "none")
    if tier == "HOT":
        parts_a = []
        if not has_site:
            parts_a.append("no website")
        if rev <= 10:
            parts_a.append(f"only {rev} reviews")
        biz["recommended_action"] = f"Walk in — {', '.join(parts_a) or 'strong fit'}. Demo the card."
    elif tier == "WARM":
        biz["recommended_action"] = f"Email — {rev} reviews, {'has' if has_site else 'no'} website. Pitch growth."
    elif tier == "MAYBE":
        biz["recommended_action"] = "Skip unless nearby or you have a connection."
    else:
        biz["recommended_action"] = "Skip — low fit score."

    return biz


def export_csv(leads, filename):
    """Export leads to CSV formatted for dashboard import."""
    if not leads:
        print_progress(f"{C.YELLOW}No leads to export.{C.RESET}")
        return

    fields = [
        "fit_score", "lead_tier", "business_name", "industry", "industry_tier",
        "address", "city", "phone", "website", "google_maps_url",
        "google_rating", "google_review_count", "is_chain",
        "score_industry", "score_reviews", "score_rating",
        "score_digital", "score_independence",
        "recommended_action", "status", "contact_date", "notes",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for lead in sorted(leads, key=lambda x: x["fit_score"], reverse=True):
            writer.writerow(lead)

    print(f"\n  {C.GREEN}{C.BOLD}✅ Exported {len(leads)} leads → {filename}{C.RESET}")
    print(f"  {C.GRAY}Import this file into your dashboard at:{C.RESET}")
    print(f"  {C.BLUE}taptech-landing.vercel.app/leads/{C.RESET}\n")


def run_scraper(locations, industries, max_per_industry=20, headless=True):
    """Main scraper pipeline."""
    all_leads = []
    seen_ids = set()

    print_banner()

    with sync_playwright() as p:
        print_progress("Launching browser...")
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = context.new_page()

        # Block images/fonts to speed things up
        page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2}", lambda route: route.abort())

        total_searches = len(locations) * len(industries)
        search_num = 0

        for location in locations:
            print(f"\n  {C.GREEN}{C.BOLD}📍 {location}{C.RESET}")
            print(f"  {C.GRAY}{'─' * 50}{C.RESET}")

            for industry in industries:
                search_num += 1
                tier = INDUSTRY_CONFIG.get(industry, {}).get("tier", "?")
                print(f"\n  {C.BLUE}[{search_num}/{total_searches}]{C.RESET} "
                      f"{C.WHITE}{industry}{C.RESET} "
                      f"{C.GRAY}(Tier {tier}){C.RESET}")

                query = f"{industry} in {location}"
                businesses = scrape_google_maps(page, query, industry, max_results=max_per_industry)

                for biz in businesses:
                    # Deduplicate by name + address
                    biz_key = f"{biz['business_name']}|{biz.get('address', '')}"
                    if biz_key not in seen_ids:
                        seen_ids.add(biz_key)
                        all_leads.append(biz)

                # Random delay between searches
                delay = 2 + random.random() * 3
                time.sleep(delay)

        try:
            context.close()
            browser.close()
        except:
            pass

    # Sort by score
    all_leads.sort(key=lambda x: x["fit_score"], reverse=True)

    # Print summary
    hot = sum(1 for l in all_leads if l["lead_tier"] == "HOT")
    warm = sum(1 for l in all_leads if l["lead_tier"] == "WARM")
    maybe = sum(1 for l in all_leads if l["lead_tier"] == "MAYBE")
    skip = sum(1 for l in all_leads if l["lead_tier"] == "SKIP")

    print(f"\n{C.GREEN}{C.BOLD}  ── Results ──{C.RESET}")
    print(f"  {C.GRAY}Total leads:{C.RESET} {C.GREEN}{C.BOLD}{len(all_leads)}{C.RESET}")
    print(f"  {C.GREEN}🔥 HOT:  {hot}{C.RESET}")
    print(f"  {C.BLUE}🟡 WARM: {warm}{C.RESET}")
    print(f"  {C.YELLOW}🔵 MAYBE: {maybe}{C.RESET}")
    print(f"  {C.RED}⚫ SKIP: {skip}{C.RESET}")

    return all_leads


def main():
    parser = argparse.ArgumentParser(
        description="TapTech Lead Scraper — Scrape Google Maps for business prospects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_leads.py "Riverside, CA"
  python scrape_leads.py "Corona, CA" --industries "barbershop,tattoo shop,nail salon"
  python scrape_leads.py "92501" --max 30
  python scrape_leads.py --batch
  python scrape_leads.py "Fontana, CA" --visible    (watch the browser)
        """,
    )

    parser.add_argument("location", nargs="?", help="City, zip code, or area to search")
    parser.add_argument("--industries", "-i", type=str, help="Comma-separated industries (default: all 20)")
    parser.add_argument("--max", type=int, default=15, help="Max results per industry per location (default: 15)")
    parser.add_argument("--output", "-o", type=str, help="Output CSV filename")
    parser.add_argument("--batch", action="store_true", help="Scan all 10 priority IE cities")
    parser.add_argument("--visible", action="store_true", help="Show browser window (not headless)")
    parser.add_argument("--top-industries", action="store_true", help="Only scan Tier A industries (top 10)")

    args = parser.parse_args()

    # Determine locations
    if args.batch:
        locations = IE_CITIES_PRIORITY
    elif args.location:
        locations = [args.location]
    else:
        parser.print_help()
        sys.exit(1)

    # Determine industries
    if args.industries:
        industries = [t.strip() for t in args.industries.split(",")]
    elif args.top_industries:
        industries = [k for k, v in INDUSTRY_CONFIG.items() if v["tier"] == "A"]
    else:
        industries = ALL_INDUSTRIES

    print_progress(f"Locations: {len(locations)} · Industries: {len(industries)} · Max per search: {args.max}")

    # Run
    leads = run_scraper(
        locations=locations,
        industries=industries,
        max_per_industry=args.max,
        headless=not args.visible,
    )

    # Export
    if leads:
        if args.output:
            filename = args.output
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            if args.batch:
                filename = f"leads_IE_{ts}.csv"
            else:
                safe = args.location.replace(",", "").replace(" ", "_").lower() if args.location else "batch"
                filename = f"leads_{safe}_{ts}.csv"

        export_csv(leads, filename)
    else:
        print(f"\n  {C.YELLOW}No leads found. Try a different location or industry.{C.RESET}\n")


if __name__ == "__main__":
    main()
