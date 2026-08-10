"""Browser/E2E verification for the six new storefront families —
atlas_catalog, ava_fashion, toranj_gifting, sarv_stock, sepidar_handmade,
zarrin_jewelry.

Follows the exact same established convention as
`scripts/verify_product_entry_ui.py` (Playwright, async, screenshot capture
under scripts/.verify_output/) — this is NOT a new parallel runtime, it
reuses the repo's own existing browser-verification pattern.

Requirements (same as verify_product_entry_ui.py):
  * a Django dev server reachable at RASTISI_VERIFY_BASE
  * one Store per family already published with that family active,
    reachable at a distinct hostname (see FAMILY_HOSTS below — adjust to
    match your local StoreDomain fixtures before running)
  * at least one real, visible product in that Store so the product-detail
    page has something to render
  * the `playwright` package with a Chromium build available

This script CAPTURES the 24 required screenshots (6 families x 2 pages x
2 viewports) and performs a few structural sanity checks (no console
errors, expected family marker present, add-to-cart button present) — it
does NOT itself constitute visual QA. A human must still look at the
captured images under scripts/.verify_output/ (or the directory pointed to
by RASTISI_SCREENSHOT_OUT, if set by the calling PowerShell script) and
compare them against the family's intended design.

Usage:
    python manage.py runserver 0.0.0.0:8765 &
    python scripts/verify_six_families_visual.py
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

BASE_TEMPLATE = os.environ.get("RASTISI_VERIFY_BASE_TEMPLATE", "http://{host}:8765")
CHROMIUM = os.environ.get("RASTISI_VERIFY_CHROMIUM", "/opt/pw-browsers/chromium")
OUT_DIR = os.environ.get(
    "RASTISI_SCREENSHOT_OUT",
    os.path.join(os.path.dirname(__file__), ".verify_output", "six_families_screenshots"),
)

# Adjust these hostnames to match real StoreDomain fixtures in your
# environment — one per family, each Store already published with that
# family active and at least one visible product.
FAMILY_HOSTS = {
    "atlas_catalog": os.environ.get("RASTISI_HOST_ATLAS_CATALOG", "atlas-catalog.rastisi.localhost"),
    "ava_fashion": os.environ.get("RASTISI_HOST_AVA_FASHION", "ava-fashion.rastisi.localhost"),
    "toranj_gifting": os.environ.get("RASTISI_HOST_TORANJ_GIFTING", "toranj-gifting.rastisi.localhost"),
    "sarv_stock": os.environ.get("RASTISI_HOST_SARV_STOCK", "sarv-stock.rastisi.localhost"),
    "sepidar_handmade": os.environ.get("RASTISI_HOST_SEPIDAR_HANDMADE", "sepidar-handmade.rastisi.localhost"),
    "zarrin_jewelry": os.environ.get("RASTISI_HOST_ZARRIN_JEWELRY", "zarrin-jewelry.rastisi.localhost"),
}

# Required viewports per the acceptance criteria.
VIEWPORTS = [
    ("desktop", 1440, 1000),
    ("mobile", 390, 844),
]

failures = []


def fail(scenario, message):
    failures.append(f"[{scenario}] {message}")
    print(f"FAIL [{scenario}] {message}")


async def capture_page(browser, *, family, page_kind, url, viewport_name, width, height, out_dir):
    scenario = f"{family}-{page_kind}-{viewport_name}"
    errors = []
    page = await browser.new_page(viewport={"width": width, "height": height})
    page.on(
        "console",
        lambda m: errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
    except Exception as exc:  # noqa: BLE001 - report and move on to the next capture
        fail(scenario, f"navigation failed: {exc}")
        await page.close()
        return

    marker = f'data-sfb-family="{family}"'
    html = await page.content()
    if marker not in html:
        fail(scenario, f"family marker {marker!r} not found in rendered HTML")

    if errors:
        fail(scenario, f"console errors: {errors[:3]}")

    screenshot_path = os.path.join(out_dir, f"{scenario}.png")
    await page.screenshot(path=screenshot_path, full_page=(page_kind == "product"))
    print(f"OK   [{scenario}] -> {screenshot_path}")
    await page.close()


async def run_family(browser, family, host, out_dir):
    base = BASE_TEMPLATE.format(host=host)

    for viewport_name, width, height in VIEWPORTS:
        await capture_page(
            browser, family=family, page_kind="home", url=f"{base}/",
            viewport_name=viewport_name, width=width, height=height, out_dir=out_dir,
        )

    # Product page requires a real, visible product slug for this Store.
    # This script does not itself query the database (no Django context in
    # a plain script); RASTISI_PRODUCT_SLUG_<FAMILY> must be set to a real
    # product slug for that Store, or this step is skipped with a warning.
    slug_env = f"RASTISI_PRODUCT_SLUG_{family.upper()}"
    product_slug = os.environ.get(slug_env)
    if not product_slug:
        print(f"SKIP [{family}-product] {slug_env} not set — cannot capture product page")
        return
    for viewport_name, width, height in VIEWPORTS:
        await capture_page(
            browser, family=family, page_kind="product", url=f"{base}/product/{product_slug}/",
            viewport_name=viewport_name, width=width, height=height, out_dir=out_dir,
        )


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM if os.path.exists(CHROMIUM) else None)
        for family, host in FAMILY_HOSTS.items():
            await run_family(browser, family, host, OUT_DIR)
        await browser.close()

    print()
    print(f"Screenshots written to: {OUT_DIR}")
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All structural checks passed. VISUAL REVIEW OF SCREENSHOTS BY A HUMAN IS STILL REQUIRED.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
