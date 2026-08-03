"""تکِ منبعِ حقیقتِ کاتالوگِ صنف — بخشِ ۲ (یک منبعِ واحد برایِ همه‌ی نقاطِ ورودی).

هر نقطه‌ی ورودی که صنف‌ها را برایِ انتخاب/فیلتر/جست‌وجو نمایش می‌دهد
(صفحه‌ی عمومیِ «صنوفِ پشتیبانی‌شده»، ساختِ فروشگاهِ جدید، آنبوردینگ،
تنظیماتِ صنفِ مرچنت) باید از همین ماژول بخواند — نه یک کوئریِ محلیِ
تکراری. هیچ فهرستِ صنفِ هاردکدشده‌ای در قالب/جاوااسکریپت/فرم وجود ندارد."""

from apps.catalog.models import IndustryTemplate

#: ترتیبِ تب‌هایِ رسته — دقیقاً طبقِ بخشِ ۴ (اولین گزینه «همه صنوف» است).
SECTOR_TABS = [("all", "همه صنوف")] + list(IndustryTemplate.Sector.choices)


def offerable_industry_templates():
    """جدیدترین نسخه‌ی «آماده‌ی تولید» و فعالِ هر صنف — یک ردیف به‌ازای هر
    ``slug`` — تنها فهرستی که برای نصبِ جدید پیشنهاد می‌شود (ADR-26/27)."""
    templates = IndustryTemplate.objects.filter(
        is_active=True, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
    ).order_by("slug", "-version")
    seen_slugs = set()
    result = []
    for template in templates:
        if template.slug in seen_slugs:
            continue
        seen_slugs.add(template.slug)
        result.append(template)
    result.sort(key=lambda t: (t.display_order, t.name))
    return result
