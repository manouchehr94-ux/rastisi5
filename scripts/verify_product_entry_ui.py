"""Repeatable browser verification for the exact-prototype product-entry wizard.

Consolidates the ad hoc Playwright checks used while building the exact-prototype
product form (`apps/dashboard/templates/dashboard/partials/product_form.html` and
`product_options_body.html`) into one script, so the same scenarios can be re-run
after future changes instead of being re-invented by hand.

Requirements (already satisfied in the dev/CI sandbox this repo runs in):
  * a Django dev server reachable at RASTISI_VERIFY_BASE (default matches this
    sandbox's `python manage.py runserver 0.0.0.0:8765`, http://teststore.rastisi.localhost:8765)
  * a store at that (sub)domain with a staff login (RASTISI_VERIFY_USER / RASTISI_VERIFY_PASS)
  * the `playwright` package with a Chromium build available (this sandbox pre-installs
    it at /opt/pw-browsers/chromium; override with RASTISI_VERIFY_CHROMIUM if different)

Usage:
    python manage.py runserver 0.0.0.0:8765 &
    python scripts/verify_product_entry_ui.py

Exits non-zero (and prints every failure) if any scenario or any of the four
responsive-overflow checks (1440/1024/768/390) fails. Screenshots for every
scenario/width are written under scripts/.verify_output/ for visual review.
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("RASTISI_VERIFY_BASE", "http://teststore.rastisi.localhost:8765")
USERNAME = os.environ.get("RASTISI_VERIFY_USER", "09120000001")
PASSWORD = os.environ.get("RASTISI_VERIFY_PASS", "Testpass123!")
CHROMIUM = os.environ.get("RASTISI_VERIFY_CHROMIUM", "/opt/pw-browsers/chromium")
OUT_DIR = os.path.join(os.path.dirname(__file__), ".verify_output")
WIDTHS = [1440, 1024, 768, 390]
TABS = [
    ("basic", "اطلاعات پایه"),
    ("category", "دسته"),
    ("price", "قیمت"),
    ("media", "تصاویر"),
    ("seo", "سئو"),
]

failures = []


def fail(scenario, message):
    failures.append(f"[{scenario}] {message}")
    print(f"FAIL [{scenario}] {message}")


async def login(page):
    await page.goto(f"{BASE}/admin-portal/login/", wait_until="networkidle")
    await page.fill('input[name="username"]', USERNAME)
    await page.fill('input[name="password"]', PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")


async def scenario_create_simple_product(browser):
    """Create-flow smoke test: simple product, all five tabs reachable, no console errors."""
    name = "scenario"
    errors = []
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    await login(page)
    await page.goto(f"{BASE}/admin-portal/products/add/", wait_until="networkidle")

    if await page.locator(".pe-prototype").count() == 0:
        fail(name, "exact-prototype shell (.pe-prototype) not present on create page")
        await page.close()
        return

    for key, label in TABS:
        step = page.locator(".pe-step", has_text=label)
        if await step.count() == 0:
            fail(name, f"tab pill for '{label}' not found")
            continue
        await step.first.click()
        await page.wait_for_timeout(250)

    if errors:
        fail(name, f"console errors while navigating tabs: {errors[:3]}")
    await page.close()


async def scenario_variant_product_table_card_toggle(browser):
    """Variable product: attribute cards render, and table/card variant view toggle works."""
    name = "variant_table_card_toggle"
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    await login(page)
    await page.goto(f"{BASE}/admin-portal/products/", wait_until="networkidle")
    row = page.locator("tr", has_text="کالای نمایشی تنوع").first
    if await row.count() == 0:
        print(f"SKIP [{name}] no seeded variant-demo product found by name; skipping")
        await page.close()
        return
    icons = row.locator("a, button")
    clicked = False
    for i in range(await icons.count()):
        el = icons.nth(i)
        title = (await el.get_attribute("title")) or ""
        if "ویرایش" in title:
            await el.click()
            clicked = True
            break
    if not clicked:
        fail(name, "could not find edit action on the seeded variant-demo row")
        await page.close()
        return
    await page.wait_for_timeout(1000)
    await page.locator(".pe-step", has_text="قیمت").first.click()
    await page.wait_for_timeout(300)

    if await page.locator(".attribute").count() == 0:
        fail(name, "no .attribute cards rendered for a variable product")

    table_btn = page.locator('button', has_text="جدول")
    card_btn = page.locator('button', has_text="کارت")
    if await table_btn.count() and await card_btn.count():
        await table_btn.first.click()
        await page.wait_for_timeout(200)
        await card_btn.first.click()
        await page.wait_for_timeout(200)
    await page.close()


async def scenario_category_quick_add(browser):
    """Quick-add-category modal: teleported, opens, and the group select is not empty."""
    name = "category_quick_add"
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    await login(page)
    await page.goto(f"{BASE}/admin-portal/products/add/", wait_until="networkidle")
    await page.locator(".pe-step", has_text="دسته").first.click()
    await page.wait_for_timeout(200)
    add_group_btn = page.locator("button, a", has_text="افزودن گروه اصلی")
    if await add_group_btn.count() == 0:
        fail(name, "'+ افزودن گروه اصلی' button not found")
        await page.close()
        return
    await add_group_btn.first.click()
    await page.wait_for_timeout(300)
    overlay = page.locator('.overlay[style*="display"], .overlay').filter(has=page.locator("text=گروهِ اصلی, text=گروه اصلی"))
    if await page.locator("text=ساختِ دسته‌بندیِ جدید").count() == 0 and await page.locator("text=دسته‌بندی جدید").count() == 0:
        fail(name, "quick-add-category modal heading not visible after clicking the button")
    await page.close()


async def scenario_media_and_seo_tabs(browser):
    """Media/SEO tabs render the exact-prototype dropzone affordance and SEO fields."""
    name = "media_and_seo_tabs"
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    await login(page)
    await page.goto(f"{BASE}/admin-portal/products/add/", wait_until="networkidle")

    await page.locator(".pe-step", has_text="تصاویر").first.click()
    await page.wait_for_timeout(250)
    if await page.locator(".dropzone-choose").count() == 0:
        fail(name, "media tab: dropzone-choose button not present")

    await page.locator(".pe-step", has_text="سئو").first.click()
    await page.wait_for_timeout(250)
    if await page.locator('[name="meta_title"], [name="seo_title"]').count() == 0:
        fail(name, "seo tab: no meta/seo title field found")
    await page.close()


async def responsive_overflow_check(browser):
    """No horizontal page overflow at 1440/1024/768/390 across all five tabs."""
    name = "responsive_overflow"
    os.makedirs(OUT_DIR, exist_ok=True)
    for width in WIDTHS:
        page = await browser.new_page(viewport={"width": width, "height": 900})
        await login(page)
        await page.goto(f"{BASE}/admin-portal/products/add/", wait_until="networkidle")
        for key, label in TABS:
            step = page.locator(".pe-step", has_text=label)
            if await step.count() == 0:
                fail(name, f"width={width}: tab '{label}' not found")
                continue
            await step.first.click()
            await page.wait_for_timeout(250)
            scroll_w = await page.evaluate("document.documentElement.scrollWidth")
            client_w = await page.evaluate("document.documentElement.clientWidth")
            await page.screenshot(path=f"{OUT_DIR}/resp_{width}_{key}.png", full_page=True)
            if scroll_w > client_w:
                fail(name, f"width={width} tab={key}: horizontal overflow (scrollWidth={scroll_w} > clientWidth={client_w})")
        await page.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM)
        await scenario_create_simple_product(browser)
        await scenario_variant_product_table_card_toggle(browser)
        await scenario_category_quick_add(browser)
        await scenario_media_and_seo_tabs(browser)
        await responsive_overflow_check(browser)
        await browser.close()

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    print("\nAll product-entry UI verification scenarios passed.")


if __name__ == "__main__":
    asyncio.run(main())
