import json
import sqlite3
import time

class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bricklink_price_cache (
                item_no TEXT PRIMARY KEY,
                avg_used_price REAL NOT NULL,
                currency_code TEXT,
                unit_quantity INTEGER,
                total_quantity INTEGER,
                fetched_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listing_analysis (
                item_id TEXT PRIMARY KEY,
                image_signature TEXT NOT NULL,
                status TEXT NOT NULL,
                figures_json TEXT NOT NULL,
                meta_json TEXT NOT NULL,
                analyzed_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listing_state (
                item_id TEXT PRIMARY KEY,
                last_price REAL,
                last_bid REAL,
                bid_count INTEGER,
                item_end_date TEXT,
                image_signature TEXT,
                last_seen REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    def get_cached_price(self, item_no, max_age_seconds):
        row = self.conn.execute(
            """
            SELECT avg_used_price, currency_code, unit_quantity,
                   total_quantity, fetched_at
            FROM bricklink_price_cache
            WHERE item_no = ?
            """,
            (item_no,),
        ).fetchone()
        if not row:
            return None

        avg_price, currency, units, total, fetched_at = row
        if time.time() - fetched_at > max_age_seconds:
            return None

        return {
            "avg_price": float(avg_price),
            "currency_code": currency,
            "unit_quantity": units,
            "total_quantity": total,
            "cached": True,
        }

    def cache_price(self, item_no, data):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO bricklink_price_cache
            (item_no, avg_used_price, currency_code,
             unit_quantity, total_quantity, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item_no,
                float(data["avg_price"]),
                data.get("currency_code"),
                data.get("unit_quantity"),
                data.get("total_quantity"),
                time.time(),
            ),
        )
        self.conn.commit()

    def get_listing_analysis(self, item_id, image_signature):
        row = self.conn.execute(
            """
            SELECT image_signature, status, figures_json, meta_json, analyzed_at
            FROM listing_analysis
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if not row:
            return None

        stored_signature, status, figures_json, meta_json, analyzed_at = row
        if stored_signature != image_signature:
            return None

        return {
            "image_signature": stored_signature,
            "status": status,
            "figures": json.loads(figures_json),
            "meta": json.loads(meta_json),
            "analyzed_at": analyzed_at,
        }

    def save_listing_analysis(
        self,
        item_id,
        image_signature,
        status,
        figures,
        meta=None,
    ):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO listing_analysis
            (item_id, image_signature, status, figures_json, meta_json, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                image_signature,
                status,
                json.dumps(figures),
                json.dumps(meta or {}),
                time.time(),
            ),
        )
        self.conn.commit()

    def save_listing_state(self, listing, image_signature):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO listing_state
            (item_id, last_price, last_bid, bid_count,
             item_end_date, image_signature, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing.get("item_id"),
                float(listing.get("price", 0) or 0),
                (
                    float(listing["current_bid_price"])
                    if listing.get("current_bid_price") is not None
                    else None
                ),
                int(listing.get("bid_count", 0) or 0),
                listing.get("item_end_date"),
                image_signature,
                time.time(),
            ),
        )
        self.conn.commit()
