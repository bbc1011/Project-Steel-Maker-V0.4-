from collections import Counter, defaultdict
from pathlib import Path

from figure_detector import isolate_figures, save_boxed_preview
from image_pipeline import prepare_unique_images, make_contact_sheet

def _select_detail_photo_numbers(
    unique_records,
    inspect_numbers,
    high_numbers,
    include_neighbors,
    max_detail,
):
    available = [r["photo_number"] for r in unique_records]
    available_set = set(available)

    ordered = []
    for number in list(high_numbers) + list(inspect_numbers):
        if number in available_set and number not in ordered:
            ordered.append(number)

    if include_neighbors:
        for number in list(ordered):
            try:
                pos = available.index(number)
            except ValueError:
                continue
            for neighbor_pos in (pos - 1, pos + 1):
                if 0 <= neighbor_pos < len(available):
                    neighbor = available[neighbor_pos]
                    if neighbor not in ordered:
                        ordered.append(neighbor)

    return ordered[:max(1, int(max_detail))]

def _recognize_photo_figures(record, figures, brickognize):
    recognized = []
    for crop in figures:
        try:
            result = brickognize.identify_pil(crop["image"])
            best = brickognize.best_candidate(result)
            if not best or not best.get("bricklink_id"):
                recognized.append({
                    "status": "unidentified",
                    "photo_number": record["photo_number"],
                    "detector_label": crop.get("label"),
                })
                continue

            recognized.append({
                "status": "identified",
                "photo_number": record["photo_number"],
                "bricklink_id": str(best["bricklink_id"]),
                "name": best.get("name"),
                "brickognize_score": float(best.get("score", 0) or 0),
            })
        except Exception as exc:
            recognized.append({
                "status": "error",
                "photo_number": record["photo_number"],
                "error": str(exc),
            })
    return recognized

def aggregate_recognized_figures(per_photo_results):
    """
    Conservative cross-photo de-duplication:
    for each BrickLink ID, use the maximum number of copies visible together
    in any one photo. This avoids counting one figure repeatedly across angles
    while still allowing two identical figures seen together to count as two.
    """
    counts_by_id = defaultdict(dict)
    best_meta = {}

    for photo_number, recognized in per_photo_results.items():
        counts = Counter(
            item["bricklink_id"]
            for item in recognized
            if item.get("status") == "identified"
        )
        for bricklink_id, count in counts.items():
            counts_by_id[bricklink_id][photo_number] = count

        for item in recognized:
            if item.get("status") != "identified":
                continue
            bricklink_id = item["bricklink_id"]
            if (
                bricklink_id not in best_meta
                or item.get("brickognize_score", 0)
                > best_meta[bricklink_id].get("brickognize_score", 0)
            ):
                best_meta[bricklink_id] = dict(item)

    aggregated = []
    for bricklink_id, by_photo in counts_by_id.items():
        meta = best_meta[bricklink_id]
        aggregated.append({
            "status": "identified",
            "bricklink_id": bricklink_id,
            "name": meta.get("name"),
            "brickognize_score": meta.get("brickognize_score", 0),
            "quantity": max(by_photo.values()),
            "observed_photo_counts": {
                str(k): int(v) for k, v in sorted(by_photo.items())
            },
        })

    return sorted(aggregated, key=lambda x: x["bricklink_id"])

def refresh_figure_prices(figures, bricklink):
    refreshed = []
    for figure in figures:
        item = dict(figure)
        bricklink_id = item.get("bricklink_id")
        if not bricklink_id:
            refreshed.append(item)
            continue

        try:
            price = bricklink.current_average_used_price(bricklink_id)
        except Exception as exc:
            price = None
            item["price_error"] = str(exc)

        item["bricklink_current_avg_used"] = (
            price.get("avg_price") if price else None
        )
        item["currency"] = price.get("currency_code") if price else None
        item["bricklink_inventory_count"] = (
            price.get("unit_quantity") if price else None
        )
        refreshed.append(item)

    return refreshed

def analyze_listing(
    listing,
    search,
    settings,
    vision,
    brickognize,
    bricklink,
):
    unique_records = prepare_unique_images(
        listing.get("image_urls", []),
        max_images=settings.max_listing_images,
        max_hash_distance=settings.image_dhash_distance,
    )

    if not unique_records:
        return {
            "status": "no_images",
            "figures": [],
            "meta": {"unique_images": 0},
        }

    print(
        f"  Local image prep: {len(unique_records)} unique photo(s) "
        f"from {min(len(listing.get('image_urls', [])), settings.max_listing_images)} downloaded candidate(s)."
    )

    overview_hits = []
    high_detail = []
    estimated_total = 0

    chunk_size = max(1, settings.contact_sheet_max_images)
    for start in range(0, len(unique_records), chunk_size):
        chunk = unique_records[start:start + chunk_size]
        sheet = make_contact_sheet(
            chunk,
            tile_size=settings.contact_sheet_tile_size,
        )
        photo_numbers = [r["photo_number"] for r in chunk]
        overview = vision.screen_contact_sheet(
            sheet,
            valid_photo_numbers=photo_numbers,
            resolution=settings.gemini_overview_resolution,
        )

        estimated_total += overview["estimated_visible_minifigures"]
        overview_hits.extend(overview["inspect_photo_numbers"])
        high_detail.extend(overview["high_detail_photo_numbers"])

        print(
            "  Gemini overview "
            f"{photo_numbers[0]}-{photo_numbers[-1]}: "
            f"{'PROMISING' if overview['promising'] else 'no minifig signal'}; "
            f"inspect={overview['inspect_photo_numbers']}"
        )

    overview_hits = list(dict.fromkeys(overview_hits))
    high_detail = list(dict.fromkeys(high_detail))

    if not overview_hits:
        print("  Cheap-screen result: listing screened out before detailed vision.")
        return {
            "status": "screened_out",
            "figures": [],
            "meta": {
                "unique_images": len(unique_records),
                "overview_estimated_figures": estimated_total,
                "overview_selected": [],
            },
        }

    detail_numbers = _select_detail_photo_numbers(
        unique_records=unique_records,
        inspect_numbers=overview_hits,
        high_numbers=high_detail,
        include_neighbors=settings.gemini_include_neighbor_photos,
        max_detail=settings.gemini_max_detail_images,
    )
    record_by_number = {
        record["photo_number"]: record for record in unique_records
    }

    per_photo_results = {}
    analyzed_numbers = []

    for photo_number in detail_numbers:
        record = record_by_number[photo_number]
        requested_high = photo_number in set(high_detail)
        first_resolution = (
            settings.gemini_high_detail_resolution
            if requested_high
            else settings.gemini_detail_resolution
        )

        detections = vision.detect_figures(
            image=record["image"],
            resolution=first_resolution,
            user_hint=search.get("detection_hint", ""),
        )
        figures = isolate_figures(
            record["image"],
            detections,
            max_figures=settings.max_figures_per_image,
        )

        # If overview saw a promising photo but medium detail found nothing,
        # invest one high-resolution retry rather than abandoning it.
        if (
            not figures
            and settings.gemini_enable_high_detail_retry
            and first_resolution != settings.gemini_high_detail_resolution
        ):
            print(
                f"  Photo {photo_number}: medium detail found 0; "
                "escalating once to high detail."
            )
            detections = vision.detect_figures(
                image=record["image"],
                resolution=settings.gemini_high_detail_resolution,
                user_hint=search.get("detection_hint", ""),
            )
            figures = isolate_figures(
                record["image"],
                detections,
                max_figures=settings.max_figures_per_image,
            )

        print(
            f"  Detail photo {photo_number}: {len(figures)} figure crop(s)."
        )

        if settings.save_boxed_previews and figures:
            safe_id = str(listing["item_id"]).replace("|", "_")
            path = (
                Path(settings.boxed_preview_dir)
                / safe_id
                / f"photo_{photo_number}.jpg"
            )
            save_boxed_preview(record["image"], figures, path)

        per_photo_results[photo_number] = _recognize_photo_figures(
            record,
            figures,
            brickognize,
        )
        analyzed_numbers.append(photo_number)

    aggregated = aggregate_recognized_figures(per_photo_results)
    priced = refresh_figure_prices(aggregated, bricklink)

    return {
        "status": "analyzed",
        "figures": priced,
        "meta": {
            "unique_images": len(unique_records),
            "overview_estimated_figures": estimated_total,
            "overview_selected": overview_hits,
            "high_detail_selected": high_detail,
            "detail_analyzed": analyzed_numbers,
        },
    }
