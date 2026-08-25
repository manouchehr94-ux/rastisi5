"""One-off forensics script (NOT a management command) — builds a
deterministic structured inventory of the 345 raw user-supplied QA images
and renders contact sheets for visual review.

Usage (from repo root, inside the app venv):
    python apps/stores/demo_assets/rasti_mode_demo/scripts/build_inventory.py [output_dir]

Outputs are scratch audit artifacts, never part of the delivered product
data — written OUTSIDE the repository by default (a temp directory) so
they can never leave confusing untracked noise in `git status`. Pass an
explicit ``output_dir`` argument to write elsewhere:
    <output_dir>/raw_inventory.json
    <output_dir>/contact_sheets/<folder>_<n>.jpg
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "raw_user_catalog"
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "rasti_mode_demo_image_audit"
SHEETS = WORK / "contact_sheets"
FOLDERS = ["1", "2", "3", "4", "5"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def average_hash(image: Image.Image, size: int = 8) -> str:
    small = image.convert("L").resize((size, size), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def dominant_colors(image: Image.Image, n: int = 3) -> list[list[int]]:
    small = image.convert("RGB").resize((64, 64))
    quant = small.quantize(colors=8, method=Image.MEDIANCUT)
    palette = quant.getpalette()
    counts = sorted(quant.getcolors(), reverse=True)
    colors = []
    for count, idx in counts[:n]:
        r, g, b = palette[idx * 3: idx * 3 + 3]
        colors.append([r, g, b])
    return colors


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def build_inventory() -> list[dict]:
    records = []
    for folder in FOLDERS:
        folder_dir = RAW / folder
        files = sorted(folder_dir.glob("*.jpg"))
        for path in files:
            with Image.open(path) as img:
                width, height = img.size
                ahash = average_hash(img)
                colors = dominant_colors(img)
                file_size = path.stat().st_size
            records.append({
                "folder": folder,
                "filename": path.name,
                "relpath": str(path.relative_to(BASE)),
                "width": width,
                "height": height,
                "aspect_ratio": round(width / height, 3),
                "file_size_bytes": file_size,
                "sha256": sha256_of(path),
                "ahash": ahash,
                "dominant_colors_rgb": colors,
            })
    return records


def flag_near_duplicates(records: list[dict], threshold: int = 4) -> None:
    by_folder: dict[str, list[dict]] = {}
    for rec in records:
        by_folder.setdefault(rec["folder"], []).append(rec)
    for folder, recs in by_folder.items():
        for rec in recs:
            rec["near_duplicate_of"] = []
        for i, a in enumerate(recs):
            for b in recs[i + 1:]:
                if hamming(a["ahash"], b["ahash"]) <= threshold:
                    a["near_duplicate_of"].append(b["filename"])
                    b["near_duplicate_of"].append(a["filename"])


def build_contact_sheets(records: list[dict], per_sheet: int = 48, cols: int = 8) -> None:
    SHEETS.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    cell = 130
    label_h = 16
    by_folder: dict[str, list[dict]] = {}
    for rec in records:
        by_folder.setdefault(rec["folder"], []).append(rec)

    for folder, recs in by_folder.items():
        recs = sorted(recs, key=lambda r: r["filename"])
        for sheet_idx in range(0, len(recs), per_sheet):
            chunk = recs[sheet_idx:sheet_idx + per_sheet]
            rows = -(-len(chunk) // cols)
            sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (255, 255, 255))
            draw = ImageDraw.Draw(sheet)
            for i, rec in enumerate(chunk):
                r, c = divmod(i, cols)
                x, y = c * cell, r * (cell + label_h)
                with Image.open(BASE / rec["relpath"]) as img:
                    thumb = img.convert("RGB").copy()
                    thumb.thumbnail((cell - 8, cell - 8))
                    px = x + (cell - thumb.width) // 2
                    py = y + (cell - thumb.height) // 2
                    sheet.paste(thumb, (px, py))
                short_name = rec["filename"].replace("_org_zoom", "").replace(".jpg", "")
                draw.text((x + 4, y + cell - 2), short_name, fill=(0, 0, 0), font=font)
            out_path = SHEETS / f"folder{folder}_{sheet_idx // per_sheet + 1}.jpg"
            sheet.save(out_path, format="JPEG", quality=80)
            print(f"wrote {out_path} ({len(chunk)} images)")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    records = build_inventory()
    flag_near_duplicates(records)
    out = WORK / "raw_inventory.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"wrote {out} ({len(records)} records)")
    build_contact_sheets(records)


if __name__ == "__main__":
    main()
