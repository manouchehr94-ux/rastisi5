"""Import the requested DamaTajhiz catalogue into one store.

This command is intentionally scoped to the five category URLs requested for
Akhlaghi. It imports up to 20 unique products per category, stores structured
technical facts, downloads product images, and activates the imported products
with a configurable initial stock.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import (
    Brand, Category, Product, Specification, SpecificationTemplate,
    SpecificationTemplateField, Vendor,
)
from apps.catalog.services.product_image_service import ProductImageError, add_product_image
from apps.stores.models import Store

SOURCE_HOST = "damatajhiz.com"
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)


@dataclass(frozen=True)
class CategorySource:
    code: str
    name: str
    slug: str
    icon: str
    url: str
    template_name: str


SOURCES = (
    CategorySource("AC", "کولر گازی و اسپلیت", "air-conditioner-split", "❄️",
        "https://damatajhiz.com/categories/34/%DA%A9%D9%88%D9%84%D8%B1-%DA%AF%D8%A7%D8%B2%DB%8C-%D9%88-%D8%A7%D8%B3%D9%BE%D9%84%DB%8C%D8%AA",
        "مشخصات کولر گازی و اسپلیت"),
    CategorySource("ALRAD", "رادیاتور آلومینیومی", "aluminium-radiator", "♨️",
        "https://damatajhiz.com/categories/8/%D8%B1%D8%A7%D8%AF%DB%8C%D8%A7%D8%AA%D9%88%D8%B1-%D8%A2%D9%84%D9%88%D9%85%DB%8C%D9%86%DB%8C%D9%88%D9%85%DB%8C",
        "مشخصات رادیاتور آلومینیومی"),
    CategorySource("PNRAD", "رادیاتور فولادی، پنلی و برقی", "panel-steel-electric-radiator", "🔥",
        "https://damatajhiz.com/categories/9/%D8%B1%D8%A7%D8%AF%DB%8C%D8%A7%D8%AA%D9%88%D8%B1-%D9%81%D9%88%D9%84%D8%A7%D8%AF%DB%8C-%D9%BE%D9%86%D9%84%DB%8C-%D8%A8%D8%B1%D9%82%DB%8C",
        "مشخصات رادیاتور فولادی، پنلی و برقی"),
    CategorySource("TOWEL", "حوله خشک‌کن", "towel-radiator", "🛁",
        "https://damatajhiz.com/categories/790/%D8%AD%D9%88%D9%84%D9%87-%D8%AE%D8%B4%DA%A9-%DA%A9%D9%86",
        "مشخصات حوله خشک‌کن"),
    CategorySource("WCOOL", "کولر آبی", "evaporative-air-cooler", "💧",
        "https://damatajhiz.com/categories/6/%DA%A9%D9%88%D9%84%D8%B1-%D8%A2%D8%A8%DB%8C",
        "مشخصات کولر آبی"),
)


@dataclass
class ParsedProduct:
    source_id: str
    source_url: str
    name: str
    brand: str | None = None
    price: Decimal = Decimal("0")
    discount_percent: int = 0
    inquiry_only: bool = True
    rating: Decimal = Decimal("0")
    description: str = ""
    specs: list[tuple[str, str]] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)


class ScrapeError(RuntimeError):
    pass


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_digits(value: str) -> str:
    return str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,."))


def extract_source_id(url: str) -> str:
    match = re.search(r"/products/(\d+)", url)
    if not match:
        raise ScrapeError(f"شناسه محصول از URL قابل استخراج نیست: {url}")
    return match.group(1)


def parse_money(value: str) -> Decimal:
    cleaned = normalize_digits(value).replace(",", "")
    matches = re.findall(r"\d{4,}", cleaned)
    if not matches:
        return Decimal("0")
    try:
        return Decimal(matches[-1])
    except InvalidOperation:
        return Decimal("0")


def unique(items: Iterable[str]) -> list[str]:
    result, seen = [], set()
    for item in items:
        item = compact_text(item)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def json_ld_objects(soup: BeautifulSoup) -> list[dict]:
    objects: list[dict] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            continue
        queue = list(payload) if isinstance(payload, list) else [payload]
        while queue:
            item = queue.pop(0)
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                queue.extend(graph)
            objects.append(item)
    return objects


def discover_product_urls(html: str, base_url: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for anchor in soup.select('a[href*="/products/"]'):
        href = anchor.get("href")
        if not href:
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0].split("?", 1)[0]
        if urlparse(absolute).netloc.endswith(SOURCE_HOST) and re.search(r"/products/\d+", absolute):
            urls.append(absolute)
    return unique(urls)[:limit]


def _product_json_ld(soup: BeautifulSoup) -> dict:
    for item in json_ld_objects(soup):
        kind = item.get("@type")
        if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
            return item
    return {}


def _extract_images(soup: BeautifulSoup, product_ld: dict, base_url: str) -> list[str]:
    candidates: list[str] = []
    ld_images = product_ld.get("image", [])
    candidates.extend([ld_images] if isinstance(ld_images, str) else (ld_images or []))
    for selector, attr in (
        ('meta[property="og:image"]', "content"), ('meta[name="twitter:image"]', "content"),
        ("main img", "src"), ('img[alt*="مدل"]', "src"),
    ):
        for node in soup.select(selector):
            value = node.get(attr) or node.get("data-src") or node.get("data-lazy-src")
            if value:
                candidates.append(value)
    output = []
    for value in unique(candidates):
        absolute = urljoin(base_url, value)
        path = urlparse(absolute).path.lower()
        if any(token in path for token in ("logo", "icon", "avatar", "namad", "banner")):
            continue
        if path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            output.append(absolute)
    return output[:6]


def _extract_specs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    specs, seen = [], set()
    def add(label: str, value: str):
        label, value = compact_text(label).strip(":"), compact_text(value)
        if not label or not value or label in seen or len(label) > 120 or len(value) > 500:
            return
        seen.add(label); specs.append((label, value))
    for row in soup.select("table tr"):
        cells = [compact_text(c.get_text(" ", strip=True)) for c in row.select("th,td")]
        if len(cells) == 2:
            add(cells[0], cells[1])
        elif len(cells) > 2:
            for i in range(0, len(cells) - 1, 2): add(cells[i], cells[i + 1])
    for dl in soup.select("dl"):
        for term, value in zip(dl.select("dt"), dl.select("dd")):
            add(term.get_text(" ", strip=True), value.get_text(" ", strip=True))
    features = []
    for li in soup.select("main li, article li, .product li, .product-detail li"):
        text = compact_text(li.get_text(" ", strip=True))
        if 8 <= len(text) <= 300 and not re.search(r"^(صفحه اصلی|تماس|خرید اقساطی|ورود|سبد)", text):
            features.append(text)
    for i, value in enumerate(unique(features)[:18], 1): add(f"ویژگی {i}", value)
    return specs[:60]


def _detect_brand(name: str, soup: BeautifulSoup) -> str | None:
    for selector in ('[itemprop="brand"]', '.brand-name', 'a[href*="/brands/"]'):
        node = soup.select_one(selector)
        if node:
            value = compact_text(node.get_text(" ", strip=True))
            if 1 < len(value) < 80:
                return value
    known = ("ایران رادیاتور", "گری", "گرین", "هایسنس", "جی پلاس", "تک الکتریک", "بوتان", "لورچ", "ایساتیس", "شوفاژکار", "آذرتهویه", "انرژی", "آبسال", "سپهر الکتریک")
    combined = f"{name} {compact_text(soup.get_text(' ', strip=True)[:3500])}"
    return next((brand for brand in known if brand in combined), None)


def _build_description(name: str, category_name: str, specs: list[tuple[str, str]]) -> str:
    facts = [f"{label}: {value}" for label, value in specs[:16]]
    text = f"{name} در دسته «{category_name}» قرار دارد. "
    if facts:
        text += "مشخصات و ویژگی‌های ثبت‌شده برای این محصول عبارت‌اند از: " + "؛ ".join(facts) + ". "
    text += "پیش از خرید، قیمت روز، موجودی، ظرفیت و تناسب مشخصات فنی با محل نصب بررسی شود."
    return text[:5000]


def parse_product_page(html: str, url: str, source: CategorySource) -> ParsedProduct:
    soup = BeautifulSoup(html, "html.parser")
    product_ld = _product_json_ld(soup)
    h1 = soup.select_one("h1")
    name = compact_text(product_ld.get("name", "")) or compact_text(h1.get_text(" ", strip=True) if h1 else "")
    if not name:
        raise ScrapeError(f"نام محصول در صفحه پیدا نشد: {url}")
    page_text = compact_text(soup.get_text(" ", strip=True))
    offers = product_ld.get("offers", {})
    if isinstance(offers, list): offers = offers[0] if offers else {}
    price = parse_money(str(offers.get("price", ""))) if isinstance(offers, dict) else Decimal("0")
    inquiry_only = "استعلام قیمت" in page_text and price == 0
    if price == 0 and not inquiry_only:
        price = parse_money(page_text[:7000])
    old_new = re.findall(r"([\d۰-۹][\d۰-۹,٬]{3,})\s*تومان", page_text[:7000])
    discount = 0
    if len(old_new) >= 2:
        old, new = parse_money(old_new[-2]), parse_money(old_new[-1])
        if old > new > 0:
            price, discount = old, max(0, min(100, int(((old-new)/old)*100)))
    rating = Decimal("0")
    aggregate = product_ld.get("aggregateRating", {})
    if isinstance(aggregate, dict):
        try: rating = Decimal(str(aggregate.get("ratingValue", "0")))
        except InvalidOperation: pass
    specs = _extract_specs(soup)
    return ParsedProduct(
        source_id=extract_source_id(url), source_url=url, name=name[:220],
        brand=_detect_brand(name, soup), price=price, discount_percent=discount,
        inquiry_only=inquiry_only or price == 0,
        rating=min(Decimal("5"), max(Decimal("0"), rating)),
        description=_build_description(name, source.name, specs), specs=specs,
        image_urls=_extract_images(soup, product_ld, url),
    )


class DamaTajhizClient:
    def __init__(self, timeout=DEFAULT_TIMEOUT, delay=0.5):
        self.timeout, self.delay = timeout, delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fa-IR,fa;q=0.9"})
    def get_text(self, url):
        r = self.session.get(url, timeout=self.timeout); r.raise_for_status(); time.sleep(self.delay); return r.text
    def get_image(self, url):
        r = self.session.get(url, timeout=self.timeout); r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").split(";", 1)[0].lower()
        ext = {"image/jpeg":".jpg", "image/png":".png", "image/webp":".webp"}.get(content_type) or Path(urlparse(url).path).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}: raise ScrapeError(f"فرمت تصویر پشتیبانی نمی‌شود: {content_type or ext}")
        return r.content, ext


class Command(BaseCommand):
    help = "ورود ۲۰ محصول از هر یک از پنج دسته درخواست‌شده دماتجهیز"
    def add_arguments(self, parser):
        parser.add_argument("--store-slug", default="akhlaghi")
        parser.add_argument("--vendor-slug", default="digimarket")
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--stock", type=int, default=10)
        parser.add_argument("--skip-images", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
        parser.add_argument("--delay", type=float, default=0.5)
    def handle(self, *args, **options):
        limit, stock = options["limit"], options["stock"]
        if not 1 <= limit <= 20: raise CommandError("--limit باید بین ۱ تا ۲۰ باشد.")
        if stock < 0: raise CommandError("--stock نمی‌تواند منفی باشد.")
        try: store = Store.objects.get(slug=options["store_slug"])
        except Store.DoesNotExist as exc: raise CommandError("فروشگاه پیدا نشد.") from exc
        try: vendor = Vendor.objects.get(store=store, slug=options["vendor_slug"])
        except Vendor.DoesNotExist as exc: raise CommandError("فروشنده موردنظر در این فروشگاه پیدا نشد.") from exc
        client = DamaTajhizClient(options["timeout"], options["delay"])
        totals = {"created":0, "updated":0, "failed":0, "images":0, "specs":0, "found":0}
        try:
            with transaction.atomic():
                for order, source in enumerate(SOURCES):
                    self.stdout.write(self.style.MIGRATE_HEADING(f"\nدسته: {source.name}"))
                    category, _ = Category.objects.update_or_create(store=store, slug=source.slug,
                        defaults={"name":source.name,"icon":source.icon,"is_active":True,"parent":None,"order":order})
                    template, _ = SpecificationTemplate.objects.update_or_create(
                        name=f"{store.slug} — {source.template_name}", defaults={"category":category})
                    urls = discover_product_urls(client.get_text(source.url), source.url, limit)
                    totals["found"] += len(urls)
                    if not urls: raise CommandError(f"هیچ محصولی در دسته {source.name} پیدا نشد.")
                    if len(urls) < limit:
                        self.stdout.write(self.style.WARNING(f"  فقط {len(urls)} محصول یکتا در منبع پیدا شد (هدف {limit})."))
                    for index, url in enumerate(urls, 1):
                        try:
                            parsed = parse_product_page(client.get_text(url), url, source)
                            created, images = self._upsert(store, vendor, category, template, source, parsed, client, stock, options["skip_images"])
                            totals["created" if created else "updated"] += 1; totals["images"] += images; totals["specs"] += len(parsed.specs)
                            self.stdout.write(self.style.SUCCESS(f"  {index:02d}. {'ایجاد' if created else 'به‌روزرسانی'}: {parsed.name}"))
                        except Exception as exc:
                            totals["failed"] += 1; self.stderr.write(self.style.ERROR(f"  {index:02d}. خطا {url}: {exc}"))
                if options["dry_run"]:
                    transaction.set_rollback(True); self.stdout.write(self.style.WARNING("\nDRY-RUN: همه تغییرات بازگردانده شد."))
        except requests.RequestException as exc: raise CommandError(f"خطای ارتباط با منبع: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            "\nپایان ورود — یافت‌شده: {found} | ایجاد: {created} | به‌روزرسانی: {updated} | تصاویر: {images} | مشخصات: {specs} | خطا: {failed}".format(**totals)))

    def _upsert(self, store, vendor, category, template, source, parsed, client, stock, skip_images):
        brand = None
        if parsed.brand:
            bslug = slugify(parsed.brand, allow_unicode=True)[:140] or f"brand-{parsed.source_id}"
            brand, _ = Brand.objects.update_or_create(store=store, slug=bslug, defaults={"name":parsed.brand})
        sku, pslug = f"DT-{source.code}-{parsed.source_id}"[:40], f"damatajhiz-{parsed.source_id}"
        product, created = Product.objects.update_or_create(store=store, sku=sku, defaults={
            "slug":pslug,"vendor":vendor,"category":category,"brand":brand,"name":parsed.name,
            "description":parsed.description,"price":parsed.price,"discount_percent":parsed.discount_percent,
            "stock":stock,"status":Product.Status.ACTIVE,"product_type":Product.ProductType.SIMPLE,
            "rating":parsed.rating,"icon":source.icon,"tag":Product.Tag.SALE if parsed.discount_percent else "",
        })
        product.full_clean(); product.save()
        product.specifications.all().delete()
        all_specs = [("شناسه منبع", parsed.source_id), ("منبع داده", parsed.source_url),
                     ("وضعیت قیمت", "نیازمند استعلام" if parsed.inquiry_only else "قیمت ثبت‌شده")] + parsed.specs
        Specification.objects.bulk_create([Specification(product=product,label=l,value=v,order=i) for i,(l,v) in enumerate(all_specs)])
        for i,(label,_value) in enumerate(parsed.specs):
            SpecificationTemplateField.objects.get_or_create(template=template,label=label,defaults={"order":i})
        image_count = 0
        if not skip_images and not product.images.exists():
            for i, image_url in enumerate(parsed.image_urls):
                try:
                    body, ext = client.get_image(image_url)
                    if len(body) > 5*1024*1024: continue
                    add_product_image(product, ContentFile(body, name=f"dt-{parsed.source_id}-{i}{ext}"), alt=parsed.name)
                    image_count += 1
                except (requests.RequestException, ScrapeError, ProductImageError, OSError) as exc:
                    self.stderr.write(self.style.WARNING(f"    تصویر رد شد: {image_url} ({exc})"))
        return created, image_count
