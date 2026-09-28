from datetime import datetime, timezone

def _total_value(figures):
    return sum(
        float(f.get("bricklink_current_avg_used", 0) or 0)
        * int(f.get("quantity", 1) or 1)
        for f in figures
        if f.get("bricklink_current_avg_used") is not None
    )

def _reference_ok(figures, wanted_ids, require_reference_match):
    if not require_reference_match:
        return True
    wanted = {str(x) for x in wanted_ids}
    return any(
        str(f.get("bricklink_id")) in wanted
        for f in figures
        if f.get("bricklink_id")
    )

def _time_remaining_minutes(end_date):
    if not end_date:
        return None
    try:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return (end - datetime.now(timezone.utc)).total_seconds() / 60
    except Exception:
        return None

def evaluate_deal(
    listing,
    figures,
    min_discount_percent,
    wanted_ids=None,
    require_reference_match=False,
    auction_early_alert_discount_percent=60,
    auction_early_min_room_usd=15,
    auction_ending_soon_minutes=60,
):
    wanted_ids = wanted_ids or set()
    shipping = float(listing.get("shipping", 0) or 0)
    estimated_value = _total_value(figures)
    reference_ok = _reference_ok(
        figures,
        wanted_ids,
        require_reference_match,
    )

    options = set(listing.get("buying_options") or [])
    pure_auction = "AUCTION" in options and "FIXED_PRICE" not in options

    priced_figure_count = sum(
        int(f.get("quantity", 1) or 1)
        for f in figures
        if f.get("bricklink_current_avg_used") is not None
    )

    if pure_auction:
        current_bid = listing.get("current_bid_price")
        if current_bid is None:
            current_bid = float(listing.get("price", 0) or 0)
        else:
            current_bid = float(current_bid)

        current_total = current_bid + shipping
        current_discount = (
            ((estimated_value - current_total) / estimated_value) * 100
            if estimated_value > 0
            else 0.0
        )

        target_total = estimated_value * (
            1 - float(min_discount_percent) / 100
        )
        max_bid = max(0.0, target_total - shipping)
        bid_room = max_bid - current_bid

        remaining_minutes = _time_remaining_minutes(
            listing.get("item_end_date")
        )
        ending_soon = (
            remaining_minutes is not None
            and 0 <= remaining_minutes <= float(auction_ending_soon_minutes)
        )

        early_opportunity = (
            estimated_value > 0
            and reference_ok
            and current_discount >= float(auction_early_alert_discount_percent)
            and bid_room >= float(auction_early_min_room_usd)
        )
        ending_opportunity = (
            estimated_value > 0
            and reference_ok
            and ending_soon
            and current_bid <= max_bid
        )

        if ending_opportunity:
            alert_type = "auction_ending_opportunity"
        elif early_opportunity:
            alert_type = "auction_early_opportunity"
        elif estimated_value > 0 and reference_ok and current_bid <= max_bid:
            alert_type = "auction_watch"
        else:
            alert_type = None

        return {
            "listing_type": "AUCTION",
            "alert_type": alert_type,
            "reference_match": reference_ok,
            "estimated_bricklink_value": estimated_value,
            "priced_figure_count": priced_figure_count,
            "shipping": shipping,
            "current_bid": current_bid,
            "current_total": current_total,
            "current_discount_percent": current_discount,
            "target_discount_percent": float(min_discount_percent),
            "max_bid": max_bid,
            "bid_room": bid_room,
            "bid_count": int(listing.get("bid_count", 0) or 0),
            "item_end_date": listing.get("item_end_date"),
            "remaining_minutes": remaining_minutes,
            "is_alert": alert_type in (
                "auction_early_opportunity",
                "auction_ending_opportunity",
            ),
        }

    listing_total = float(listing.get("price", 0) or 0) + shipping
    discount_percent = (
        ((estimated_value - listing_total) / estimated_value) * 100
        if estimated_value > 0
        else 0.0
    )
    is_deal = (
        estimated_value > 0
        and discount_percent >= float(min_discount_percent)
        and reference_ok
    )

    return {
        "listing_type": "FIXED_PRICE",
        "alert_type": "buy_it_now_deal" if is_deal else None,
        "reference_match": reference_ok,
        "listing_total": listing_total,
        "estimated_bricklink_value": estimated_value,
        "priced_figure_count": priced_figure_count,
        "discount_percent": discount_percent,
        "is_alert": is_deal,
        "is_deal": is_deal,
    }
