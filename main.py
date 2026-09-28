import json
import time

from config import settings
from database import Database
from ebay_client import EbayClient
from brickognize_client import BrickognizeClient
from bricklink_client import BrickLinkClient
from reference_resolver import resolve_reference_ids
from figure_detector import GeminiVision
from gemini_usage import GeminiUsageTracker
from image_pipeline import image_signature
from listing_analyzer import analyze_listing, refresh_figure_prices
from deal_engine import evaluate_deal

def load_searches():
    with open(settings.search_config, "r", encoding="utf-8") as f:
        return json.load(f)

def build_clients(database, usage_tracker):
    ebay = EbayClient(
        settings.ebay_client_id,
        settings.ebay_client_secret,
        settings.ebay_marketplace_id,
    )
    brickognize = BrickognizeClient(
        min_similarity=settings.brickognize_min_similarity,
        top_k=settings.brickognize_top_k,
    )
    bricklink = BrickLinkClient(
        consumer_key=settings.bricklink_consumer_key,
        consumer_secret=settings.bricklink_consumer_secret,
        token_value=settings.bricklink_token_value,
        token_secret=settings.bricklink_token_secret,
        database=database,
        cache_hours=settings.price_cache_hours,
        currency_code=settings.bricklink_currency,
        country_code=settings.bricklink_country_code,
    )
    vision = GeminiVision(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        thinking_level=settings.gemini_thinking_level,
        usage_tracker=usage_tracker,
    )
    return ebay, brickognize, bricklink, vision

def local_search_skip(listing, search):
    title = listing.get("title", "").lower()
    excluded = [
        str(x).lower().strip()
        for x in search.get("pre_screen_exclude_title_terms", [])
        if str(x).strip()
    ]
    return any(term in title for term in excluded)

def print_figures(figures):
    if not figures:
        print("  No priced minifigures cached.")
        return
    for fig in figures:
        price = fig.get("bricklink_current_avg_used")
        price_text = f"${price:.2f}" if price is not None else "no price"
        qty = int(fig.get("quantity", 1) or 1)
        print(
            f"  {qty}x {fig.get('name')} | "
            f"{fig.get('bricklink_id')} | "
            f"Brickognize {fig.get('brickognize_score', 0):.2f} | "
            f"BL current avg used {price_text}"
        )

def print_result(listing, result, cache_status):
    print(f"  Vision state: {cache_status}")

    if result["listing_type"] == "AUCTION":
        print(
            f"  Auction: bid=${result['current_bid']:.2f} + "
            f"shipping=${result['shipping']:.2f} | "
            f"BL value=${result['estimated_bricklink_value']:.2f}"
        )
        print(
            f"  Target max bid=${result['max_bid']:.2f} | "
            f"room=${result['bid_room']:.2f} | "
            f"current-value gap={result['current_discount_percent']:.1f}% | "
            f"bids={result['bid_count']}"
        )
        if result.get("remaining_minutes") is not None:
            print(
                f"  Time remaining: "
                f"{max(0, result['remaining_minutes']) / 60:.1f} hour(s)"
            )

        if result["alert_type"] == "auction_early_opportunity":
            print("\n*** EARLY AUCTION OPPORTUNITY ***")
        elif result["alert_type"] == "auction_ending_opportunity":
            print("\n*** ENDING-SOON AUCTION OPPORTUNITY ***")
        elif result["alert_type"] == "auction_watch":
            print("  Auction is below target max bid; monitoring.")
        else:
            print("  Auction not currently inside target opportunity range.")
    else:
        print(
            f"  Buy It Now: total=${result['listing_total']:.2f} | "
            f"BL value=${result['estimated_bricklink_value']:.2f} | "
            f"discount={result['discount_percent']:.1f}%"
        )
        if result["is_deal"]:
            print("\n*** BUY IT NOW DEAL ***")

    if result.get("is_alert"):
        print(f"URL: {listing.get('item_web_url', '')}")

def run_once():
    searches = load_searches()
    db = Database(settings.db_path)

    usage_tracker = GeminiUsageTracker(
        max_calls=settings.gemini_max_calls_per_cycle,
        log_usage=settings.gemini_log_usage,
        input_price_per_million=settings.gemini_input_price_per_million,
        output_price_per_million=settings.gemini_output_price_per_million,
    )
    ebay, brickognize, bricklink, vision = build_clients(
        db, usage_tracker
    )

    # One item can appear in several searches. Full eBay detail and vision
    # analysis are shared across all searches in the same cycle.
    cycle_listing_cache = {}

    print(f"Starting {len(searches)} search(es) sequentially.")

    for search in searches:
        name = search.get("name", search.get("query", "Unnamed search"))
        print(f"\n===== {name} =====")

        wanted_ids, references = resolve_reference_ids(
            brickognize=brickognize,
            reference_paths=search.get("reference_images", []),
            explicit_ids=search.get("wanted_bricklink_ids", []),
        )

        if wanted_ids:
            print("Target BrickLink IDs:", ", ".join(sorted(wanted_ids)))

        try:
            listings = ebay.search(
                query=search.get("query", ""),
                filters=search.get("filters", {}),
                max_results=search.get("max_results", 20),
            )
        except Exception as exc:
            print(f"eBay search failed: {exc}")
            continue

        print(f"eBay returned {len(listings)} listing(s).")

        for summary in listings:
            item_id = summary.get("item_id")
            if not item_id:
                continue

            if local_search_skip(summary, search):
                print(f"\nLocal pre-screen skipped: {summary.get('title')}")
                continue

            if item_id in cycle_listing_cache:
                listing = cycle_listing_cache[item_id]
            else:
                listing = ebay.enrich_listing(summary)
                cycle_listing_cache[item_id] = listing

            sig = image_signature(listing.get("image_urls", []))
            cached = db.get_listing_analysis(item_id, sig)

            print(f"\nChecking: {listing.get('title', '')}")

            if cached is None:
                if not usage_tracker.can_call():
                    print(
                        "  Gemini cycle call guardrail reached; "
                        "new visual analysis deferred."
                    )
                    continue

                try:
                    analysis = analyze_listing(
                        listing=listing,
                        search=search,
                        settings=settings,
                        vision=vision,
                        brickognize=brickognize,
                        bricklink=bricklink,
                    )
                    db.save_listing_analysis(
                        item_id=item_id,
                        image_signature=sig,
                        status=analysis["status"],
                        figures=analysis["figures"],
                        meta=analysis["meta"],
                    )
                    cache_status = f"NEW {analysis['status']}"
                    figures = analysis["figures"]
                except Exception as exc:
                    print(f"  Listing analysis failed: {exc}")
                    continue
            else:
                cache_status = f"CACHED {cached['status']}"
                # Refresh BrickLink values without rerunning Gemini/Brickognize.
                figures = refresh_figure_prices(
                    cached["figures"],
                    bricklink,
                )

            print_figures(figures)

            result = evaluate_deal(
                listing=listing,
                figures=figures,
                min_discount_percent=search.get(
                    "min_discount_percent", 25
                ),
                wanted_ids=wanted_ids,
                require_reference_match=search.get(
                    "require_reference_match", False
                ),
                auction_early_alert_discount_percent=search.get(
                    "auction_early_alert_discount_percent", 60
                ),
                auction_early_min_room_usd=search.get(
                    "auction_early_min_room_usd", 15
                ),
                auction_ending_soon_minutes=search.get(
                    "auction_ending_soon_minutes", 60
                ),
            )

            print_result(listing, result, cache_status)
            db.save_listing_state(listing, sig)

    usage = usage_tracker.summary()
    print(
        "\nGemini cycle totals: "
        f"calls={usage['calls']}, "
        f"input={usage['input_tokens']}, "
        f"output={usage['output_tokens']}, "
        f"thought={usage['thought_tokens']}, "
        f"estimated_cost=${usage['estimated_cost_usd']:.6f}"
    )

def main():
    while True:
        run_once()
        if not settings.continuous_scan:
            break
        print(
            f"\nWaiting {settings.scan_interval_minutes} minute(s)..."
        )
        time.sleep(max(1, settings.scan_interval_minutes) * 60)

if __name__ == "__main__":
    main()
