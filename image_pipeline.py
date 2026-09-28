import hashlib
import io
import math

import requests
from PIL import Image, ImageDraw, ImageFont

def download_image(url):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")

def dhash(image, hash_size=8):
    gray = image.convert("L").resize(
        (hash_size + 1, hash_size),
        Image.Resampling.LANCZOS,
    )
    pixels = list(gray.getdata())
    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            value <<= 1
            value |= pixels[offset + col] > pixels[offset + col + 1]
    return value

def hamming_distance(a, b):
    return (a ^ b).bit_count()

def prepare_unique_images(urls, max_images=12, max_hash_distance=6):
    records = []
    hashes = []

    for original_number, url in enumerate(urls[:max_images], start=1):
        try:
            image = download_image(url)
            image_hash = dhash(image)

            if any(
                hamming_distance(image_hash, old_hash) <= max_hash_distance
                for old_hash in hashes
            ):
                print(f"  Photo {original_number}: local near-duplicate skipped.")
                continue

            hashes.append(image_hash)
            records.append({
                "photo_number": original_number,
                "url": url,
                "image": image,
                "dhash": f"{image_hash:016x}",
            })
        except Exception as exc:
            print(f"  Photo {original_number}: download failed: {exc}")

    return records

def image_signature(urls):
    joined = "\n".join(str(x).strip() for x in urls if x)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()

def make_contact_sheet(records, tile_size=300):
    if not records:
        raise ValueError("Cannot create a contact sheet with no photos.")

    count = len(records)
    columns = min(4, count)
    rows = math.ceil(count / columns)
    label_height = 34
    gap = 8

    width = columns * tile_size + (columns + 1) * gap
    height = rows * (tile_size + label_height) + (rows + 1) * gap

    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for i, record in enumerate(records):
        row = i // columns
        col = i % columns
        x = gap + col * tile_size
        y = gap + row * (tile_size + label_height)

        source = record["image"].copy()
        source.thumbnail(
            (tile_size, tile_size),
            Image.Resampling.LANCZOS,
        )

        tile = Image.new("RGB", (tile_size, tile_size), "white")
        tx = (tile_size - source.width) // 2
        ty = (tile_size - source.height) // 2
        tile.paste(source, (tx, ty))
        sheet.paste(tile, (x, y))

        label = f"PHOTO {record['photo_number']}"
        draw.rectangle(
            (x, y + tile_size, x + tile_size, y + tile_size + label_height),
            outline="black",
            width=1,
        )
        draw.text(
            (x + 8, y + tile_size + 9),
            label,
            fill="black",
            font=font,
        )

    return sheet
