import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")

@dataclass
class Settings:
    ebay_client_id: str = os.getenv("EBAY_CLIENT_ID", "")
    ebay_client_secret: str = os.getenv("EBAY_CLIENT_SECRET", "")
    ebay_marketplace_id: str = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_thinking_level: str = os.getenv("GEMINI_THINKING_LEVEL", "low")
    gemini_overview_resolution: str = os.getenv(
        "GEMINI_OVERVIEW_RESOLUTION", "medium"
    )
    gemini_detail_resolution: str = os.getenv(
        "GEMINI_DETAIL_RESOLUTION", "medium"
    )
    gemini_high_detail_resolution: str = os.getenv(
        "GEMINI_HIGH_DETAIL_RESOLUTION", "high"
    )
    gemini_enable_high_detail_retry: bool = _bool(
        "GEMINI_ENABLE_HIGH_DETAIL_RETRY", True
    )

    contact_sheet_max_images: int = int(
        os.getenv("CONTACT_SHEET_MAX_IMAGES", "12")
    )
    contact_sheet_tile_size: int = int(
        os.getenv("CONTACT_SHEET_TILE_SIZE", "300")
    )
    max_listing_images: int = int(os.getenv("MAX_LISTING_IMAGES", "12"))
    gemini_max_detail_images: int = int(
        os.getenv("GEMINI_MAX_DETAIL_IMAGES", "5")
    )
    gemini_include_neighbor_photos: bool = _bool(
        "GEMINI_INCLUDE_NEIGHBOR_PHOTOS", True
    )
    image_dhash_distance: int = int(os.getenv("IMAGE_DHASH_DISTANCE", "6"))

    gemini_max_calls_per_cycle: int = int(
        os.getenv("GEMINI_MAX_CALLS_PER_CYCLE", "100")
    )
    gemini_log_usage: bool = _bool("GEMINI_LOG_USAGE", True)
    gemini_input_price_per_million: float = float(
        os.getenv("GEMINI_INPUT_PRICE_PER_MILLION", "0.75")
    )
    gemini_output_price_per_million: float = float(
        os.getenv("GEMINI_OUTPUT_PRICE_PER_MILLION", "3.75")
    )

    brickognize_min_similarity: float = float(
        os.getenv("BRICKOGNIZE_MIN_SIMILARITY", "0.72")
    )
    brickognize_top_k: int = int(os.getenv("BRICKOGNIZE_TOP_K", "5"))

    bricklink_consumer_key: str = os.getenv("BRICKLINK_CONSUMER_KEY", "")
    bricklink_consumer_secret: str = os.getenv("BRICKLINK_CONSUMER_SECRET", "")
    bricklink_token_value: str = os.getenv("BRICKLINK_TOKEN_VALUE", "")
    bricklink_token_secret: str = os.getenv("BRICKLINK_TOKEN_SECRET", "")
    bricklink_country_code: str = os.getenv("BRICKLINK_COUNTRY_CODE", "")
    bricklink_currency: str = os.getenv("BRICKLINK_CURRENCY", "USD")
    price_cache_hours: float = float(os.getenv("PRICE_CACHE_HOURS", "6"))

    search_config: str = os.getenv("SEARCH_CONFIG", "searches.json")
    continuous_scan: bool = _bool("CONTINUOUS_SCAN", False)
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))

    max_figures_per_image: int = int(os.getenv("MAX_FIGURES_PER_IMAGE", "20"))
    save_boxed_previews: bool = _bool("SAVE_BOXED_PREVIEWS", True)
    boxed_preview_dir: str = os.getenv("BOXED_PREVIEW_DIR", "debug_boxes")

    db_path: str = os.getenv("DB_PATH", "deal_finder.db")

settings = Settings()
