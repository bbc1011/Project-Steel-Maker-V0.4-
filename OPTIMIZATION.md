# Gemini Optimization Guide — v0.4 Adaptive

v0.4 changes the scanner from "analyze several photos for every listing" to
"spend AI only when the listing earns it."

## Pipeline

1. eBay search/filtering
2. Full eBay item details for a new listing
3. Local image download + perceptual near-duplicate removal
4. One contact-sheet overview for most listings
5. Stop immediately if the overview sees no minifigure signal
6. Inspect only selected promising photos
7. Escalate a difficult photo to high resolution only when needed
8. Brickognize identifies cropped figures
9. Cross-photo de-duplication
10. BrickLink prices the identified figures
11. Cache the visual analysis
12. Future five-minute cycles update price/bids/time without rerunning vision

## Bogus / irrelevant listings

The contact-sheet overview is intentionally recall-oriented. It does not try to
identify exact minifigures. It only decides whether a listing contains enough
visual minifigure evidence to justify a detailed scan.

A listing screened out by the overview is cached, so the same unchanged listing
does not spend another Gemini request next cycle.

Optional exact title exclusions can be placed in each search under:

    "pre_screen_exclude_title_terms": ["instructions only", "manual only"]

Keep this list conservative; aggressive title filtering can hide real deals.

## Adaptive image processing

Default:

    GEMINI_OVERVIEW_RESOLUTION=medium
    GEMINI_DETAIL_RESOLUTION=medium
    GEMINI_HIGH_DETAIL_RESOLUTION=high
    GEMINI_ENABLE_HIGH_DETAIL_RETRY=true

Overview runs on a numbered montage of up to 12 unique listing photos.
Detailed calls happen only for photos selected by the overview, plus optional
neighboring photos, capped by:

    GEMINI_MAX_DETAIL_IMAGES=5

This replaces the old "stop after one photo fails to improve" rule, which could
miss a valuable later photo.

## Photo de-duplication

Before Gemini, v0.4 computes a local dHash for each downloaded photo.
Near-duplicates are removed without an AI call.

Default:

    IMAGE_DHASH_DISTANCE=6

## Cross-photo minifigure counting

v0.4 no longer values only one "best" photo.

Brickognize can identify figures in several promising photos. To avoid counting
the same physical figure repeatedly across different angles, v0.4 uses a
conservative rule:

For each BrickLink ID, quantity = the maximum number of that ID visible
together in any single analyzed photo.

Example:
- photo 1 contains two identical clone troopers
- photo 2 contains one of those same clones close-up
- photo 3 contains both again

Quantity remains 2, not 5.

This is conservative: two identical figures photographed separately and never
shown together can be undercounted. A later version can add true visual
cross-photo instance tracking.

## Auctions

Buy It Now:
- compare current purchase price + shipping against BrickLink value
- alert immediately if it meets the requested discount

Auction:
- current bid is NOT treated as the final purchase price
- calculate a target maximum bid
- flag a very low early auction as an opportunity
- flag an ending-soon auction if it is still below the target max bid

Example search controls:

    "min_discount_percent": 30,
    "auction_early_alert_discount_percent": 60,
    "auction_early_min_room_usd": 15,
    "auction_ending_soon_minutes": 60

For $100 BrickLink value and $5 shipping at a 30% target discount:

    target total cost = $70
    maximum bid = $65

## Analyze once, monitor cheaply

The SQLite database stores the visual analysis keyed by:
- eBay item ID
- image URL signature

If the listing returns with the same image signature, Gemini and Brickognize are
not rerun. BrickLink prices can refresh through the existing price cache, while
eBay bid/price/time data is reevaluated every search cycle.

If the image URL signature changes, the listing becomes eligible for a fresh
visual analysis.

## Call guardrail

    GEMINI_MAX_CALLS_PER_CYCLE=100

When reached, new visual analysis is deferred. Previously cached listings can
still be evaluated without Gemini.

## Testing

Start with:

    CONTINUOUS_SCAN=false
    GEMINI_MAX_CALLS_PER_CYCLE=30
    GEMINI_LOG_USAGE=true

and 10-20 representative listings.

Review:
- how many listings stop after overview
- whether overview misses minifigure listings
- which photos are escalated
- Brickognize recognition confidence
- Gemini token totals and estimated cost
