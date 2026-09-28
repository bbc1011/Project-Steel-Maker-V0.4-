# LEGO Deal Finder v0.4 — Adaptive Vision + Auction Logic

v0.4 is built around one rule:

> Spend expensive image analysis only when a listing looks promising.

## Pipeline

eBay → local photo dedupe → Gemini contact-sheet triage → selected detailed
Gemini boxes → local crops → Brickognize → BrickLink current average USED price
→ Buy It Now / auction deal logic.

## Major v0.4 changes

- Contact-sheet screening before detailed Gemini calls.
- Local near-duplicate photo removal.
- No "stop after one non-improving photo" rule.
- Adaptive selection across the entire listing, so later photos can still win.
- Medium detail by default; high detail only for difficult/promising photos.
- Cross-photo minifigure aggregation instead of valuing only one photo.
- Cached vision results: unchanged listings are not reprocessed every 5 minutes.
- The same eBay item can appear in multiple searches without paying for vision
  again.
- Buy It Now and auctions use different deal logic.
- Auctions get:
  - current bid
  - target maximum bid
  - remaining bid room
  - early-opportunity alert
  - ending-soon opportunity alert
- BrickLink price refresh remains independent of Gemini.
- Gemini call/token/cost logging remains enabled.

No Discord integration is included yet.

## Setup

Windows PowerShell:

    py -3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt

Copy:

    .env.example

to:

    .env

Then add your eBay, Gemini, and BrickLink credentials.

Never upload `.env` to GitHub.

## Run once

    python main.py

## Repeat every five minutes

In `.env`:

    CONTINUOUS_SCAN=true
    SCAN_INTERVAL_MINUTES=5

## Recommended first test

Use:

    CONTINUOUS_SCAN=false
    GEMINI_MAX_CALLS_PER_CYCLE=30
    GEMINI_LOG_USAGE=true

and set each search to 10-20 results.

## Search configuration

See `searches.json`.

Important deal settings:

    "min_discount_percent": 25,
    "auction_early_alert_discount_percent": 60,
    "auction_early_min_room_usd": 15,
    "auction_ending_soon_minutes": 60

`min_discount_percent` also determines the auction maximum-bid calculation.

## Current BrickLink valuation

BrickLink requests remain:

    guide_type=stock
    new_or_used=U

The app uses `avg_price`, meaning the current average USED asking price rather
than completed-sale average.

## Reference images

Reference-image behavior is unchanged.

Place images under `references/` and list them under:

    "reference_images": ["references/example/front.jpg"]

Brickognize resolves them to BrickLink IDs. With:

    "require_reference_match": true

a listing must contain a matching identified BrickLink ID before it can alert.

## Debug previews

With:

    SAVE_BOXED_PREVIEWS=true

detailed photos with detected figures are saved under:

    debug_boxes/<item-id>/

## Local self-test

No API credentials are required:

    python SELF_TEST.py

This checks:
- image-hash duplicate behavior
- cross-photo quantity aggregation
- Buy It Now math
- auction maximum-bid math

## More detail

Read `OPTIMIZATION.md` for the full adaptive scanning design.
