import io
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

class BrickognizeClient:
    BASE_URL = "https://api.brickognize.com"
    FIG_ENDPOINT = "/predict/figs/"

    def __init__(self, min_similarity=0.72, top_k=5):
        self.min_similarity = float(min_similarity)
        self.top_k = int(top_k)

    @staticmethod
    def _bricklink_id(candidate):
        # Prefer the BrickLink external link because it makes the mapping
        # explicit even if Brickognize changes its internal ID convention.
        for site in candidate.get("external_sites", []):
            if str(site.get("name", "")).lower() != "bricklink":
                continue

            url = site.get("url", "")
            query = parse_qs(urlparse(url).query)

            # BrickLink minifigure catalog URLs typically use M=<id>.
            for key in ("M", "P", "S"):
                if query.get(key):
                    return query[key][0]

        # Brickognize figure IDs commonly line up with catalog IDs;
        # this fallback keeps the app usable if no external link is present.
        return candidate.get("id")

    def identify_bytes(self, image_bytes, filename="figure.jpg"):
        files = [
            ("query_image", (filename, image_bytes, "image/jpeg"))
        ]
        params = {
            "top_k_items": self.top_k,
            "min_similarity_items": self.min_similarity,
        }

        r = requests.post(
            self.BASE_URL + self.FIG_ENDPOINT,
            params=params,
            files=files,
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()

        candidates = []
        for item in data.get("items", []):
            candidate = dict(item)
            candidate["bricklink_id"] = self._bricklink_id(candidate)
            candidates.append(candidate)

        return {
            "listing_id": data.get("listing_id"),
            "bounding_box": data.get("bounding_box"),
            "candidates": candidates,
        }

    def identify_pil(self, image):
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=95)
        return self.identify_bytes(buf.getvalue())

    def identify_file(self, path):
        p = Path(path)
        with p.open("rb") as f:
            content = f.read()
        return self.identify_bytes(content, filename=p.name)

    def best_candidate(self, result):
        candidates = result.get("candidates", [])
        return candidates[0] if candidates else None
