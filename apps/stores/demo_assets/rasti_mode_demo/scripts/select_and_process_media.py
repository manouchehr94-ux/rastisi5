"""Step 4/5 tooling (one-off script, NOT a management command).

Reads the curated SELECTION table below (built from real visual review of
the 345 raw QA images — see the execution ledger for the audit trail),
copies/derives exactly 150 final product images (50 products x 3), and
writes the deterministic media manifest required by the mission.

Rule for images 02/03 (mission Step 4's "no true second/third photo"
contingency — true here for every product, since the raw pool is a flat
collection of single studio photos, one per item, not multi-angle sets):
  01.webp = the real source photo, only resized/canvas-normalized
            (NOT destructively cropped) to 1200x1600.
  02.webp = a derived, non-destructive tighter crop (centered ~82% zoom)
            of the SAME real source photo, then normalized to 1200x1600.
  03.webp = a derived alternate crop (centered ~70% zoom, slightly
            off-center per a deterministic offset) of the SAME real
            source photo, then normalized to 1200x1600.
Both derived images are flagged `"derived": true` in the manifest with an
explicit transformation description, per the mission's requirement.

Usage:
    python apps/stores/demo_assets/rasti_mode_demo/scripts/select_and_process_media.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "raw_user_catalog"
OUT = BASE / "products"
MANIFEST_PATH = BASE / "selected_product_media_manifest.json"

CANVAS_W, CANVAS_H = 1200, 1600  # 3:4 portrait
WEBP_QUALITY = 88

# SKU -> (category_fa, product_title_fa, brand, dominant_color_fa, raw_folder, raw_filename)
SELECTION = [
    ("FSH-001", "کتانی رانینگ", "کتانی رانینگ چانکی سبز-کرم", "Demo Motion", "سبز", "1", "1_org_zoom-1.jpg"),
    ("FSH-002", "کتانی رانینگ", "کتانی رانینگ بندی مشکی", "Demo Motion", "مشکی", "1", "1_org_zoom-13.jpg"),
    ("FSH-003", "کتانی رانینگ", "کتانی رانینگ سبک آبی روشن", "Demo Urban", "آبی روشن", "1", "1_org_zoom-18.jpg"),
    ("FSH-004", "کتانی رانینگ", "کتانی رانینگ دد-شو کرم", "Demo Motion", "کرم", "1", "1_org_zoom-31.jpg"),
    ("FSH-005", "کتانی رانینگ", "کتانی رانینگ مسابقه‌ای مشکی-سفید", "Demo Motion", "مشکی", "1", "1_org_zoom-50.jpg"),

    ("FSH-006", "کتانی کژوال", "کتانی کژوال راه‌راه سرمه‌ای", "Demo Urban", "سرمه‌ای", "1", "1_org_zoom-38.jpg"),
    ("FSH-007", "کتانی کژوال", "کتانی کژوال کلاسیک مشکی", "Demo Urban", "مشکی", "1", "1_org_zoom-60.jpg"),
    ("FSH-008", "کتانی کژوال", "کتانی کژوال بلند صورتی", "Demo Urban", "صورتی", "1", "1_org_zoom-27.jpg"),
    ("FSH-009", "کتانی کژوال", "کتانی کژوال بلند مشکی", "Demo Motion", "مشکی", "1", "1_org_zoom-6.jpg"),
    ("FSH-010", "کتانی کژوال", "کتانی کژوال ساده سفید", "Demo Urban", "سفید", "1", "1_org_zoom-45.jpg"),

    ("FSH-011", "شلوار کژوال", "شلوار کتان کژوال سرمه‌ای", "Demo Denim", "سرمه‌ای", "2", "0_org_zoom-12.jpg"),
    ("FSH-012", "شلوار کژوال", "شلوار کتان کژوال قهوه‌ای تیره", "Demo Denim", "قهوه‌ای", "2", "0_org_zoom-22.jpg"),
    ("FSH-013", "شلوار کژوال", "شلوار کتان مشکی روزمره", "Demo Urban", "مشکی", "2", "0_org_zoom-5.jpg"),
    ("FSH-014", "شلوار کژوال", "شلوار کتان کرم ریلکس", "Demo Denim", "کرم", "2", "1_org_zoom-146.jpg"),
    ("FSH-015", "شلوار کژوال", "شلوار کتان زیتونی کژوال", "Demo Denim", "زیتونی", "2", "1_org_zoom-159.jpg"),

    ("FSH-016", "شلوار جین", "شلوار جین طوسی راسته", "Demo Denim", "طوسی", "2", "1_org_zoom-114.jpg"),
    ("FSH-017", "شلوار جین", "شلوار جین آبی متوسط اسلیم", "Demo Denim", "آبی", "2", "1_org_zoom-120.jpg"),
    ("FSH-018", "شلوار جین", "شلوار جین آبی روشن مام‌فیت", "Demo Denim", "آبی روشن", "2", "1_org_zoom-181.jpg"),
    ("FSH-019", "شلوار جین", "شلوار جین آبی ریلکس‌فیت", "Demo Layer", "آبی روشن", "2", "1_org_zoom-193.jpg"),
    ("FSH-020", "شلوار جین", "شلوار جین آبی راسته کلاسیک", "Demo Denim", "آبی", "2", "1_org_zoom-197.jpg"),

    ("FSH-021", "کاپشن و بامبر", "کاپشن بامبر زیتونی", "Demo Layer", "زیتونی", "3", "1_org_zoom-109.jpg"),
    ("FSH-022", "کاپشن و بامبر", "کاپشن بامبر کالج مشکی-کرم", "Demo Layer", "مشکی", "3", "1_org_zoom-56.jpg"),
    ("FSH-023", "کاپشن و بامبر", "کاپشن بامبر کالج زیتونی-کرم", "Demo Layer", "زیتونی", "3", "1_org_zoom-63.jpg"),
    ("FSH-024", "کاپشن و بامبر", "هودی زیپ‌دار آبی", "Demo Urban", "آبی", "3", "1_org_zoom-143.jpg"),
    ("FSH-025", "کاپشن و بامبر", "کاپشن بامبر دودی", "Demo Motion", "دودی", "3", "1_org_zoom-141.jpg"),

    ("FSH-026", "ژاکت چرم و اورشرت", "ژاکت چرم مشکی موتوری", "Demo Layer", "مشکی", "3", "1_org_zoom-111.jpg"),
    ("FSH-027", "ژاکت چرم و اورشرت", "ژاکت جین آبی کلاسیک", "Demo Denim", "آبی", "3", "1_org_zoom-3.jpg"),
    ("FSH-028", "ژاکت چرم و اورشرت", "اورشرت کتان خاکی", "Demo Layer", "خاکی", "3", "1_org_zoom-233.jpg"),
    ("FSH-029", "ژاکت چرم و اورشرت", "اورشرت زیپ‌دار قرمز", "Demo Layer", "قرمز", "3", "1_org_zoom-236.jpg"),
    ("FSH-030", "ژاکت چرم و اورشرت", "اورشرت زیتونی تیره", "Demo Muse", "زیتونی", "3", "1_org_zoom-138.jpg"),

    ("FSH-031", "کفش زنانه", "کفش تخت زنانه کرم", "Demo Muse", "کرم", "4", "0_org_zoom-10.jpg"),
    ("FSH-032", "کفش زنانه", "کفش پاشنه‌بلند قهوه‌ای", "Demo Muse", "قهوه‌ای", "4", "0_org_zoom-25.jpg"),
    ("FSH-033", "کفش زنانه", "بوت مچی زنانه مشکی", "Demo Muse", "مشکی", "4", "0_org_zoom-57.jpg"),
    ("FSH-034", "کفش زنانه", "کفش مویل زنانه قهوه‌ای", "Demo Urban", "قهوه‌ای", "4", "0_org_zoom-6.jpg"),
    ("FSH-035", "کفش زنانه", "کفش لوفر زنانه مشکی", "Demo Muse", "مشکی", "4", "0_org_zoom-79.jpg"),

    ("FSH-036", "صندل و دمپایی", "صندل جواهرنشان قهوه‌ای", "Demo Muse", "قهوه‌ای", "4", "0_org_zoom-19.jpg"),
    ("FSH-037", "صندل و دمپایی", "دمپایی حلقه‌ای مشکی", "Demo Muse", "مشکی", "4", "0_org_zoom-22.jpg"),
    ("FSH-038", "صندل و دمپایی", "دمپایی حلقه‌ای سبز تیره", "Demo Muse", "سبز", "4", "0_org_zoom-36.jpg"),
    ("FSH-039", "صندل و دمپایی", "صندل تسمه‌ای قهوه‌ای", "Demo Urban", "قهوه‌ای", "4", "0_org_zoom-41.jpg"),
    ("FSH-040", "صندل و دمپایی", "دمپایی اسلاید زیتونی", "Demo Muse", "زیتونی", "4", "0_org_zoom-69.jpg"),

    ("FSH-041", "کیف دستی و Tote", "کیف تُت چرم مشکی", "Demo Carry", "مشکی", "5", "0_org_zoom-13.jpg"),
    ("FSH-042", "کیف دستی و Tote", "کیف تُت زیتونی", "Demo Carry", "زیتونی", "5", "0_org_zoom-21.jpg"),
    ("FSH-043", "کیف دستی و Tote", "کیف تُت جیر قهوه‌ای", "Demo Carry", "قهوه‌ای", "5", "0_org_zoom-35.jpg"),
    ("FSH-044", "کیف دستی و Tote", "کیف تُت روزمره مشکی", "Demo Urban", "مشکی", "5", "1_org_zoom-41.jpg"),
    ("FSH-045", "کیف دستی و Tote", "کیف تُت خاکی بزرگ", "Demo Carry", "خاکی", "5", "1_org_zoom-44.jpg"),

    ("FSH-046", "کیف دوشی و مجلسی", "کیف دوشی چرم قهوه‌ای", "Demo Carry", "قهوه‌ای", "5", "0_org_zoom-1.jpg"),
    ("FSH-047", "کیف دوشی و مجلسی", "کیف دوشی مشکی کلاسیک", "Demo Carry", "مشکی", "5", "0_org_zoom-11.jpg"),
    ("FSH-048", "کیف دوشی و مجلسی", "کیف دوشی زنجیری مشکی", "Demo Muse", "مشکی", "5", "0_org_zoom-45.jpg"),
    ("FSH-049", "کیف دوشی و مجلسی", "کیف مجلسی زرد شنیونی", "Demo Carry", "زرد", "5", "0_org_zoom-56.jpg"),
    ("FSH-050", "کیف دوشی و مجلسی", "کیف دوشی زنجیردار مشکی", "Demo Carry", "مشکی", "5", "1_org_zoom-28.jpg"),
]

assert len(SELECTION) == 50
assert len({row[0] for row in SELECTION}) == 50
assert len({(row[5], row[6]) for row in SELECTION}) == 50, "raw source images must be unique across products"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_canvas(img: Image.Image, zoom: float = 1.0, offset: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
    """Places the (optionally center-cropped) source image onto a neutral
    1200x1600 canvas without destructively losing the product silhouette.

    zoom=1.0 uses the full source frame (image 01). zoom<1.0 crops a
    centered (optionally offset) fraction of the source frame first — this
    is the "safe detail crop / tighter non-destructive crop" derivation
    used for images 02/03.
    """
    img = img.convert("RGB")
    w, h = img.size
    if zoom < 1.0:
        crop_w, crop_h = w * zoom, h * zoom
        cx, cy = w / 2 + offset[0] * w, h / 2 + offset[1] * h
        left = max(0, min(w - crop_w, cx - crop_w / 2))
        top = max(0, min(h - crop_h, cy - crop_h / 2))
        img = img.crop((int(left), int(top), int(left + crop_w), int(top + crop_h)))
        w, h = img.size

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (247, 246, 243))
    scale = min(CANVAS_W / w, CANVAS_H / h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    px = (CANVAS_W - new_w) // 2
    py = (CANVAS_H - new_h) // 2
    canvas.paste(resized, (px, py))
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    for sku, category_fa, title_fa, brand, color_fa, folder, filename in SELECTION:
        raw_path = RAW / folder / filename
        raw_bytes = raw_path.read_bytes()
        raw_sha = sha256_bytes(raw_bytes)
        product_dir = OUT / sku
        product_dir.mkdir(parents=True, exist_ok=True)

        with Image.open(raw_path) as src:
            variants = [
                ("01.webp", False, "cover — full source frame, canvas-normalized only (no crop)", normalize_canvas(src, zoom=1.0)),
                ("02.webp", True, "derived — centered 82% non-destructive crop, canvas-normalized", normalize_canvas(src, zoom=0.82, offset=(0.0, -0.03))),
                ("03.webp", True, "derived — centered 70% non-destructive crop (slight offset), canvas-normalized", normalize_canvas(src, zoom=0.70, offset=(0.02, 0.02))),
            ]
            for order, (fname, derived, transform_desc, canvas) in enumerate(variants, start=1):
                final_path = product_dir / fname
                canvas.save(final_path, format="WEBP", quality=WEBP_QUALITY)
                final_bytes = final_path.read_bytes()
                manifest.append({
                    "sku": sku,
                    "image_order": order,
                    "cover": order == 1,
                    "raw_source_relpath": str(raw_path.relative_to(BASE)),
                    "raw_source_sha256": raw_sha,
                    "final_relpath": str(final_path.relative_to(BASE)),
                    "final_sha256": sha256_bytes(final_bytes),
                    "derived": derived,
                    "transformation": transform_desc,
                    "category": category_fa,
                    "product_title_fa": title_fa,
                    "brand": brand,
                    "dominant_color_fa": color_fa,
                    "provenance_status": "user_supplied_qa_source",
                })

    assert len(manifest) == 150
    assert len({m["final_relpath"] for m in manifest}) == 150, "duplicate final target paths"

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"wrote {MANIFEST_PATH} ({len(manifest)} entries)")
    print(f"wrote {len(SELECTION)} product folders under {OUT}")


if __name__ == "__main__":
    main()
