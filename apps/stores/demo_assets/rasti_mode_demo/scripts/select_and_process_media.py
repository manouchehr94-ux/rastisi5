"""Step 4/5 tooling (one-off script, NOT a management command).

Reads the curated SELECTION table below (built from real visual review of
the 345 raw QA images — see the execution ledger for the audit trail),
copies/derives exactly 150 final product images (50 products x 3), and
writes the deterministic media manifest required by the mission.

Post-demo hardening pass — genuine multi-color products (mission Issue 2):
8 of the 50 products are honest colorway groups, verified by direct visual
comparison to actually be the same garment/silhouette photographed in
different real colors (never two different models forced together). Each
color entry in ``SELECTION`` is a real, distinct source photo (or, for the
one product whose two colors were photographed together in a single frame
— the drawstring jogger trouser — a non-destructive left/right half-crop
of that one shared photo, which is still a genuine, undistorted, complete
depiction of each side's real garment).

Rule for single-color products (mission Step 4's "no true second/third
photo" contingency — true for every single-color product here, since the
raw pool is a flat collection of single studio photos, one per item, not
multi-angle sets):
  01.webp = the real source photo, only resized/canvas-normalized
            (NOT destructively cropped) to 1200x1600.
  02.webp = a derived, non-destructive tighter crop (centered ~82% zoom)
            of the SAME real source photo, then normalized to 1200x1600.
  03.webp = a derived alternate crop (centered ~70% zoom, slightly
            off-center per a deterministic offset) of the SAME real
            source photo, then normalized to 1200x1600.

Rule for multi-color products: each declared color gets its OWN real,
full-frame image (never a crop of another color's photo) — one image slot
per color, in the order declared. If a multi-color product declares fewer
than 3 colors, the remaining slot(s) are filled with a derived crop of the
FIRST (cover) color's real photo, flagged `"derived": true`, exactly like
the single-color contingency above — never a fabricated color.

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

# SKU -> (category_fa, product_title_fa, brand, color_entries)
#
# color_entries: an ordered list of (color_fa, folder, filename, crop_box).
# crop_box is None for a normal, dedicated real photo. It is a
# (x0, y0, x1, y1) fractional box only for the one case where two real
# colors were photographed together in a single shared frame (the
# drawstring jogger, folder 2 file 0_org_zoom-34.jpg) — extracting the
# genuinely distinct, undistorted real garment on each side.
#
# len(color_entries) == 1  -> ordinary single-color product.
# len(color_entries) >= 2  -> genuine multi-color product (mission Issue 2).

_JOGGER_LEFT = (0.0, 0.0, 0.5, 1.0)
_JOGGER_RIGHT = (0.5, 0.0, 1.0, 1.0)

SELECTION = [
    ("FSH-001", "کتانی رانینگ", "کتانی رانینگ چانکی سبز-کرم", "Demo Motion", [("سبز", "1", "1_org_zoom-1.jpg", None)]),
    ("FSH-002", "کتانی رانینگ", "کتانی رانینگ بندی مشکی", "Demo Motion", [("مشکی", "1", "1_org_zoom-13.jpg", None)]),
    ("FSH-003", "کتانی رانینگ", "کتانی رانینگ سبک آبی روشن", "Demo Urban", [("آبی روشن", "1", "1_org_zoom-18.jpg", None)]),
    ("FSH-004", "کتانی رانینگ", "کتانی رانینگ چانکی کلاسیک", "Demo Motion", [
        ("کرم", "1", "1_org_zoom-31.jpg", None),
        ("سفید", "1", "1_org_zoom-9.jpg", None),
    ]),
    ("FSH-005", "کتانی رانینگ", "کتانی رانینگ مسابقه‌ای مشکی-سفید", "Demo Motion", [("مشکی", "1", "1_org_zoom-50.jpg", None)]),

    ("FSH-006", "کتانی کژوال", "کتانی کژوال کلاسیک راه‌راه", "Demo Urban", [
        ("مشکی", "1", "1_org_zoom-38.jpg", None),
        ("سفید", "1", "1_org_zoom-11.jpg", None),
    ]),
    ("FSH-007", "کتانی کژوال", "کتانی کژوال کلاسیک مشکی", "Demo Urban", [("مشکی", "1", "1_org_zoom-60.jpg", None)]),
    ("FSH-008", "کتانی کژوال", "کتانی کژوال بلند کلاسیک", "Demo Urban", [
        ("سفید-صورتی", "1", "1_org_zoom-27.jpg", None),
        ("مشکی", "1", "1_org_zoom-6.jpg", None),
    ]),
    ("FSH-009", "کتانی کژوال", "کتانی کژوال اسپرت سفید-مشکی", "Demo Motion", [("سفید", "1", "1_org_zoom-24.jpg", None)]),
    ("FSH-010", "کتانی کژوال", "کتانی کژوال ساده سفید", "Demo Urban", [("سفید", "1", "1_org_zoom-45.jpg", None)]),

    ("FSH-011", "شلوار کژوال", "شلوار کتان کژوال سرمه‌ای", "Demo Denim", [("سرمه‌ای", "2", "0_org_zoom-12.jpg", None)]),
    ("FSH-012", "شلوار کژوال", "شلوار کتان بندی کژوال", "Demo Denim", [
        ("بژ", "2", "0_org_zoom-34.jpg", _JOGGER_LEFT),
        ("سرمه‌ای", "2", "0_org_zoom-34.jpg", _JOGGER_RIGHT),
    ]),
    ("FSH-013", "شلوار کژوال", "شلوار کتان مشکی روزمره", "Demo Urban", [("مشکی", "2", "0_org_zoom-5.jpg", None)]),
    ("FSH-014", "شلوار کژوال", "شلوار کتان کرم ریلکس", "Demo Denim", [("کرم", "2", "1_org_zoom-146.jpg", None)]),
    ("FSH-015", "شلوار کژوال", "شلوار کتان زیتونی کژوال", "Demo Denim", [("زیتونی", "2", "1_org_zoom-159.jpg", None)]),

    ("FSH-016", "شلوار جین", "شلوار جین طوسی راسته", "Demo Denim", [("طوسی", "2", "1_org_zoom-114.jpg", None)]),
    ("FSH-017", "شلوار جین", "شلوار جین آبی متوسط اسلیم", "Demo Denim", [("آبی", "2", "1_org_zoom-120.jpg", None)]),
    ("FSH-018", "شلوار جین", "شلوار جین آبی روشن مام‌فیت", "Demo Denim", [("آبی روشن", "2", "1_org_zoom-181.jpg", None)]),
    ("FSH-019", "شلوار جین", "شلوار جین آبی ریلکس‌فیت", "Demo Layer", [("آبی روشن", "2", "1_org_zoom-193.jpg", None)]),
    ("FSH-020", "شلوار جین", "شلوار جین آبی راسته کلاسیک", "Demo Denim", [("آبی", "2", "1_org_zoom-197.jpg", None)]),

    ("FSH-021", "کاپشن و بامبر", "کاپشن بامبر زیتونی", "Demo Layer", [("زیتونی", "3", "1_org_zoom-109.jpg", None)]),
    # NOTE: 1_org_zoom-56/-67/-69/-76/-185.jpg are all byte-identical
    # duplicates of the same cream-black photo in the raw pool (verified
    # via sha256) — only cream-black (via -56) and olive-cream (-63) are
    # genuinely distinct real colors of this jacket, so this is honestly a
    # 2-color product, not 3 (the 3rd image slot is a derived crop of the
    # cover color, per _build_multi_color_images' 2-color padding rule).
    ("FSH-022", "کاپشن و بامبر", "کاپشن بامبر کالج", "Demo Layer", [
        ("کرم-مشکی", "3", "1_org_zoom-56.jpg", None),
        ("زیتونی-کرم", "3", "1_org_zoom-63.jpg", None),
    ]),
    ("FSH-023", "کاپشن و بامبر", "کاپشن بامبر مشکی ساده", "Demo Layer", [("مشکی", "3", "1_org_zoom-144.jpg", None)]),
    ("FSH-024", "کاپشن و بامبر", "هودی زیپ‌دار آبی", "Demo Urban", [("آبی", "3", "1_org_zoom-143.jpg", None)]),
    ("FSH-025", "کاپشن و بامبر", "کاپشن بامبر دودی", "Demo Motion", [("دودی", "3", "1_org_zoom-141.jpg", None)]),

    # NOTE (Issue 8 — trademark visual consistency audit): -111 showed a
    # visible real third-party brand tag/wordmark on the zipper pull
    # ("...PINO") when viewed at full resolution — swapped for -25, a
    # visually equivalent black leather moto jacket with no visible
    # third-party branding.
    ("FSH-026", "ژاکت چرم و اورشرت", "ژاکت چرم مشکی موتوری", "Demo Layer", [("مشکی", "3", "1_org_zoom-25.jpg", None)]),
    ("FSH-027", "ژاکت چرم و اورشرت", "ژاکت جین آبی کلاسیک", "Demo Denim", [("آبی", "3", "1_org_zoom-3.jpg", None)]),
    ("FSH-028", "ژاکت چرم و اورشرت", "اورشرت کتان خاکی", "Demo Layer", [("خاکی", "3", "1_org_zoom-233.jpg", None)]),
    ("FSH-029", "ژاکت چرم و اورشرت", "اورشرت زیپ‌دار قرمز", "Demo Layer", [("قرمز", "3", "1_org_zoom-236.jpg", None)]),
    ("FSH-030", "ژاکت چرم و اورشرت", "اورشرت زیتونی تیره", "Demo Muse", [("زیتونی", "3", "1_org_zoom-138.jpg", None)]),

    ("FSH-031", "کفش زنانه", "کفش تخت زنانه کرم", "Demo Muse", [("کرم", "4", "0_org_zoom-10.jpg", None)]),
    ("FSH-032", "کفش زنانه", "کفش پاشنه‌بلند قهوه‌ای", "Demo Muse", [("قهوه‌ای", "4", "0_org_zoom-25.jpg", None)]),
    ("FSH-033", "کفش زنانه", "بوت مچی زنانه مشکی", "Demo Muse", [("مشکی", "4", "0_org_zoom-57.jpg", None)]),
    ("FSH-034", "کفش زنانه", "کفش مویل زنانه قهوه‌ای", "Demo Urban", [("قهوه‌ای", "4", "0_org_zoom-6.jpg", None)]),
    ("FSH-035", "کفش زنانه", "کفش لوفر زنانه مشکی", "Demo Muse", [("مشکی", "4", "0_org_zoom-79.jpg", None)]),

    ("FSH-036", "صندل و دمپایی", "صندل جواهرنشان قهوه‌ای", "Demo Muse", [("قهوه‌ای", "4", "0_org_zoom-19.jpg", None)]),
    # NOTE: -22 was previously used here as a lone "black ring-thong" but is
    # actually the same heart-charm thong as FSH-040 (verified by direct
    # visual comparison) — moved there as a genuine 3rd color; replaced here
    # with -74, a genuinely distinct plain black thong sandal.
    ("FSH-037", "صندل و دمپایی", "دمپایی انگشتی کلاسیک مشکی", "Demo Muse", [("مشکی", "4", "0_org_zoom-74.jpg", None)]),
    ("FSH-038", "صندل و دمپایی", "دمپایی حلقه‌ای سبز تیره", "Demo Muse", [("سبز", "4", "0_org_zoom-36.jpg", None)]),
    # NOTE: -43 (previously here) is a completely different flat knot-strap
    # sandal, not a colorway of the -8 double-buckle platform slide — caught
    # on visual re-verification and swapped for -26, a genuinely matching
    # double-buckle platform slide in grey-taupe suede.
    ("FSH-039", "صندل و دمپایی", "صندل دوبنده", "Demo Urban", [
        ("مشکی", "4", "0_org_zoom-8.jpg", None),
        ("طوسی", "4", "0_org_zoom-26.jpg", None),
    ]),
    ("FSH-040", "صندل و دمپایی", "دمپایی قلب‌نشان", "Demo Muse", [
        ("کرم", "4", "0_org_zoom-9.jpg", None),
        ("قهوه‌ای", "4", "0_org_zoom-91.jpg", None),
        ("مشکی", "4", "0_org_zoom-22.jpg", None),
    ]),

    ("FSH-041", "کیف دستی و Tote", "کیف تُت چرم مشکی", "Demo Carry", [("مشکی", "5", "0_org_zoom-13.jpg", None)]),
    ("FSH-042", "کیف دستی و Tote", "کیف تُت زیتونی", "Demo Carry", [("زیتونی", "5", "0_org_zoom-21.jpg", None)]),
    ("FSH-043", "کیف دستی و Tote", "کیف تُت جیر قهوه‌ای", "Demo Carry", [("قهوه‌ای", "5", "0_org_zoom-35.jpg", None)]),
    ("FSH-044", "کیف دستی و Tote", "کیف تُت روزمره مشکی", "Demo Urban", [("مشکی", "5", "1_org_zoom-41.jpg", None)]),
    ("FSH-045", "کیف دستی و Tote", "کیف تُت خاکی بزرگ", "Demo Carry", [("خاکی", "5", "1_org_zoom-44.jpg", None)]),

    ("FSH-046", "کیف دوشی و مجلسی", "کیف دوشی چرم قهوه‌ای", "Demo Carry", [("قهوه‌ای", "5", "0_org_zoom-1.jpg", None)]),
    ("FSH-047", "کیف دوشی و مجلسی", "کیف دوشی مشکی کلاسیک", "Demo Carry", [("مشکی", "5", "0_org_zoom-11.jpg", None)]),
    ("FSH-048", "کیف دوشی و مجلسی", "کیف دوشی زنجیری مشکی", "Demo Muse", [("مشکی", "5", "0_org_zoom-45.jpg", None)]),
    ("FSH-049", "کیف دوشی و مجلسی", "کیف مجلسی شنیونی", "Demo Carry", [
        ("زرد", "5", "0_org_zoom-56.jpg", None),
        ("مشکی", "5", "0_org_zoom-3.jpg", None),
    ]),
    # NOTE (Issue 8 — trademark visual consistency audit): -28 showed a
    # clearly visible real luxury-brand wordmark + logo tag on the strap —
    # swapped for -24, a visually equivalent black chain-strap bag with no
    # visible third-party branding.
    ("FSH-050", "کیف دوشی و مجلسی", "کیف دوشی زنجیردار مشکی", "Demo Carry", [("مشکی", "5", "0_org_zoom-24.jpg", None)]),
]

assert len(SELECTION) == 50
assert len({row[0] for row in SELECTION}) == 50

_multi_color_count = sum(1 for row in SELECTION if len(row[4]) >= 2)
assert _multi_color_count == 8, f"expected exactly 8 multi-color products, got {_multi_color_count}"

# Every (folder, filename, crop_box) triple must be unique across the whole
# selection — a raw photo (or, for the jogger case, a specific half-crop of
# one) is never reused across two different products.
_all_sources = [(f, n, cb) for row in SELECTION for _c, f, n, cb in row[4]]
assert len(_all_sources) == len(set(_all_sources)), "duplicate raw source (folder, filename, crop_box) across products"


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


def _load_source(folder: str, filename: str, crop_box) -> Image.Image:
    """Loads a raw source photo, optionally extracting a fractional
    sub-region first (only used for the jogger dual-color shared photo) —
    the result is treated as this color's own "full frame" from here on."""
    img = Image.open(RAW / folder / filename).convert("RGB")
    if crop_box is None:
        return img
    w, h = img.size
    x0, y0, x1, y1 = crop_box
    return img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


def _build_single_color_images(color_fa: str, folder: str, filename: str, crop_box) -> list[dict]:
    src = _load_source(folder, filename, crop_box)
    return [
        {"color_fa": color_fa, "derived": False, "transformation": "cover — full source frame, canvas-normalized only (no crop)", "canvas": normalize_canvas(src, zoom=1.0)},
        {"color_fa": color_fa, "derived": True, "transformation": "derived — centered 82% non-destructive crop, canvas-normalized", "canvas": normalize_canvas(src, zoom=0.82, offset=(0.0, -0.03))},
        {"color_fa": color_fa, "derived": True, "transformation": "derived — centered 70% non-destructive crop (slight offset), canvas-normalized", "canvas": normalize_canvas(src, zoom=0.70, offset=(0.02, 0.02))},
    ]


def _build_multi_color_images(color_entries: list[tuple[str, str, str, tuple | None]]) -> list[dict]:
    images = []
    for color_fa, folder, filename, crop_box in color_entries[:3]:
        src = _load_source(folder, filename, crop_box)
        note = "cover" if not images else "additional real color"
        crop_note = " (half-crop of a shared two-color source photo)" if crop_box is not None else ""
        images.append({
            "color_fa": color_fa, "derived": False,
            "transformation": f"{note} — real full-frame photo for this exact color{crop_note}, canvas-normalized only (no crop beyond the declared half)" if crop_box else f"{note} — real full-frame photo for this exact color, canvas-normalized only (no crop)",
            "canvas": normalize_canvas(src, zoom=1.0),
        })
    while len(images) < 3:
        cover_color, cover_folder, cover_filename, cover_crop_box = color_entries[0]
        src = _load_source(cover_folder, cover_filename, cover_crop_box)
        images.append({
            "color_fa": cover_color, "derived": True,
            "transformation": "derived — centered 82% non-destructive crop of the cover color's real photo, canvas-normalized",
            "canvas": normalize_canvas(src, zoom=0.82, offset=(0.0, -0.03)),
        })
    return images


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    for sku, category_fa, title_fa, brand, color_entries in SELECTION:
        product_dir = OUT / sku
        product_dir.mkdir(parents=True, exist_ok=True)

        if len(color_entries) == 1:
            color_fa, folder, filename, crop_box = color_entries[0]
            images = _build_single_color_images(color_fa, folder, filename, crop_box)
        else:
            images = _build_multi_color_images(color_entries)

        for order, spec in enumerate(images, start=1):
            final_path = product_dir / f"0{order}.webp"
            spec["canvas"].save(final_path, format="WEBP", quality=WEBP_QUALITY)
            final_bytes = final_path.read_bytes()

            # raw provenance always points at the real, un-cropped source
            # file that image traces to (crop_box is recorded separately —
            # the raw file's own hash is over the ENTIRE original file).
            source_color, source_folder, source_filename, source_crop = next(
                (c, f, n, cb) for c, f, n, cb in color_entries if c == spec["color_fa"]
            )
            raw_path = RAW / source_folder / source_filename
            raw_bytes = raw_path.read_bytes()

            manifest.append({
                "sku": sku,
                "image_order": order,
                "cover": order == 1,
                "raw_source_relpath": str(raw_path.relative_to(BASE)),
                "raw_source_sha256": sha256_bytes(raw_bytes),
                "final_relpath": str(final_path.relative_to(BASE)),
                "final_sha256": sha256_bytes(final_bytes),
                "derived": spec["derived"],
                "transformation": spec["transformation"],
                "category": category_fa,
                "product_title_fa": title_fa,
                "brand": brand,
                "dominant_color_fa": spec["color_fa"],
                "provenance_status": "user_supplied_qa_source",
                "multi_color_product": len(color_entries) >= 2,
            })

    assert len(manifest) == 150
    assert len({m["final_relpath"] for m in manifest}) == 150, "duplicate final target paths"

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"wrote {MANIFEST_PATH} ({len(manifest)} entries)")
    print(f"wrote {len(SELECTION)} product folders under {OUT}")
    print(f"multi-color products: {_multi_color_count}")


if __name__ == "__main__":
    main()
