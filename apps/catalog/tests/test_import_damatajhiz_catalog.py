from django.test import SimpleTestCase
from apps.catalog.management.commands.import_damatajhiz_catalog import SOURCES, discover_product_urls, parse_product_page

CATEGORY_HTML='''<a href="/products/101/first">1</a><a href="https://damatajhiz.com/products/102/second">2</a><a href="/products/101/first">dup</a><a href="https://example.com/products/9/no">x</a>'''
PRODUCT_HTML='''<html><head><meta property="og:image" content="https://cdn.example.test/p.webp"><script type="application/ld+json">{"@type":"Product","name":"کولر گازی گری 12000 مدل TEST","image":["https://cdn.example.test/p.webp"],"aggregateRating":{"ratingValue":"4.7"},"offers":{"price":"104958000"}}</script></head><body><main><h1>TEST</h1><table><tr><th>ظرفیت</th><td>12000 BTU</td></tr><tr><th>کمپرسور</th><td>روتاری</td></tr></table><ul><li>سرمایش و گرمایش</li></ul></main></body></html>'''
INQUIRY_HTML='''<main><h1>رادیاتور مدل TEST</h1><div>استعلام قیمت</div><table><tr><td>جنس</td><td>آلومینیوم</td></tr></table></main>'''

class DamaTajhizParserTests(SimpleTestCase):
    def test_requested_five_sources_are_configured(self):
        self.assertEqual(len(SOURCES), 5)
        self.assertEqual([s.code for s in SOURCES], ["AC","ALRAD","PNRAD","TOWEL","WCOOL"])
    def test_discovers_unique_internal_links(self):
        self.assertEqual(discover_product_urls(CATEGORY_HTML,"https://damatajhiz.com/categories/1/x",20), ["https://damatajhiz.com/products/101/first","https://damatajhiz.com/products/102/second"])
    def test_parses_product_facts(self):
        parsed=parse_product_page(PRODUCT_HTML,"https://damatajhiz.com/products/101/test",SOURCES[0])
        self.assertEqual(parsed.price,104958000); self.assertFalse(parsed.inquiry_only)
        self.assertIn(("ظرفیت","12000 BTU"),parsed.specs); self.assertIn("مشخصات و ویژگی‌های ثبت‌شده",parsed.description)
    def test_inquiry_product(self):
        parsed=parse_product_page(INQUIRY_HTML,"https://damatajhiz.com/products/202/test",SOURCES[1])
        self.assertEqual(parsed.price,0); self.assertTrue(parsed.inquiry_only)
