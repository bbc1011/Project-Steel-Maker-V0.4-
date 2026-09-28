import base64
import io
import json
from pathlib import Path

from PIL import ImageDraw
from google import genai

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "promising": {"type": "boolean"},
        "inspect_photo_numbers": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "high_detail_photo_numbers": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "estimated_visible_minifigures": {"type": "integer"},
    },
    "required": [
        "promising",
        "inspect_photo_numbers",
        "high_detail_photo_numbers",
        "estimated_visible_minifigures",
    ],
}

BOX_SCHEMA = {
    "type": "object",
    "properties": {
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "box_2d": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "label": {"type": "string"},
                },
                "required": ["box_2d", "label"],
            },
        }
    },
    "required": ["boxes"],
}

def _image_to_jpeg_b64(image, quality=88):
    buf = io.BytesIO()
    image.convert("RGB").save(
        buf,
        format="JPEG",
        quality=quality,
        optimize=True,
    )
    return base64.b64encode(buf.getvalue()).decode("utf-8")

class GeminiVision:
    def __init__(
        self,
        api_key,
        model,
        thinking_level="low",
        usage_tracker=None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.thinking_level = thinking_level
        self.usage_tracker = usage_tracker

    def _call(self, prompt, image, resolution, schema):
        if self.usage_tracker is not None and not self.usage_tracker.can_call():
            raise RuntimeError("Gemini per-cycle call guardrail reached.")

        interaction = self.client.interactions.create(
            model=self.model,
            input=[
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "data": _image_to_jpeg_b64(image),
                    "mime_type": "image/jpeg",
                    "resolution": resolution,
                },
            ],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
            generation_config={
                "thinking_level": self.thinking_level,
            },
        )

        if self.usage_tracker is not None:
            self.usage_tracker.record(interaction)

        return json.loads(interaction.output_text)

    def screen_contact_sheet(self, sheet, valid_photo_numbers, resolution="medium"):
        valid_text = ", ".join(str(x) for x in valid_photo_numbers)
        prompt = f"""
This is a numbered contact sheet from one eBay LEGO listing.

Your ONLY job is cheap visual triage:
- Decide whether ANY photo appears to contain one or more LEGO minifigures,
  including partially hidden minifigures.
- If yes, return the photo numbers most worth inspecting at full detail.
- Put crowded, distant, blurry, or very small-minifigure photos in
  high_detail_photo_numbers.
- Do not identify characters, sets, catalog IDs, or prices.
- Ignore loose bricks, boxes, manuals, vehicles, and standalone body parts
  unless an actual minifigure is also visible.

Valid photo numbers: {valid_text}

Be recall-oriented: if a photo might contain a minifigure, include it.
""".strip()

        data = self._call(
            prompt=prompt,
            image=sheet,
            resolution=resolution,
            schema=OVERVIEW_SCHEMA,
        )

        valid = set(valid_photo_numbers)
        inspect = [
            int(x) for x in data.get("inspect_photo_numbers", [])
            if int(x) in valid
        ]
        high = [
            int(x) for x in data.get("high_detail_photo_numbers", [])
            if int(x) in valid
        ]

        return {
            "promising": bool(data.get("promising")) or bool(inspect),
            "inspect_photo_numbers": inspect,
            "high_detail_photo_numbers": high,
            "estimated_visible_minifigures": int(
                data.get("estimated_visible_minifigures", 0) or 0
            ),
        }

    def detect_figures(
        self,
        image,
        resolution="medium",
        user_hint="",
    ):
        prompt = f"""
Locate every complete or mostly complete LEGO minifigure visible in this photo.

Return one bounding box per physical minifigure.
Do NOT identify characters, sets, or catalog IDs.
Do NOT box loose bricks, standalone helmets, loose heads, vehicles,
packaging, manuals, or unrelated objects.

Coordinates must be [ymin, xmin, ymax, xmax], normalized from 0 to 1000.

Extra detection hint:
{user_hint or "None."}
""".strip()

        data = self._call(
            prompt=prompt,
            image=image,
            resolution=resolution,
            schema=BOX_SCHEMA,
        )
        boxes = data.get("boxes", [])
        return boxes if isinstance(boxes, list) else []

def _pixel_box(box_2d, width, height, padding=0.08):
    ymin, xmin, ymax, xmax = [
        max(0, min(1000, int(v))) for v in box_2d
    ]

    left = int(xmin / 1000 * width)
    top = int(ymin / 1000 * height)
    right = int(xmax / 1000 * width)
    bottom = int(ymax / 1000 * height)

    bw = max(1, right - left)
    bh = max(1, bottom - top)
    px = int(bw * padding)
    py = int(bh * padding)

    return (
        max(0, left - px),
        max(0, top - py),
        min(width, right + px),
        min(height, bottom + py),
    )

def isolate_figures(image, detections, max_figures=20):
    width, height = image.size
    figures = []

    for index, detection in enumerate(detections[:max_figures]):
        box = detection.get("box_2d")
        if not isinstance(box, list) or len(box) != 4:
            continue

        pixel_box = _pixel_box(box, width, height)
        left, top, right, bottom = pixel_box
        if right - left < 35 or bottom - top < 35:
            continue

        figures.append({
            "index": index,
            "label": detection.get("label", "minifigure"),
            "box_2d": box,
            "pixel_box": pixel_box,
            "image": image.crop(pixel_box).copy(),
        })

    return figures

def save_boxed_preview(image, figures, output_path):
    preview = image.copy()
    draw = ImageDraw.Draw(preview)

    for i, fig in enumerate(figures, start=1):
        left, top, right, bottom = fig["pixel_box"]
        draw.rectangle((left, top, right, bottom), width=4)
        draw.text((left + 4, max(0, top - 16)), f"Fig {i}")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(path)
