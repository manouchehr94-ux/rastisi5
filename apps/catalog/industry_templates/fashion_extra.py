"""صنایع تکمیلیِ پوشاک/اکسسوری (Phase 1F): ساعت، عینک، کیف و چمدان.

نگاه کنید به ``apps/catalog/seed_data/industry_templates.py`` برای فرمت
پایه و ``apps/catalog/industry_templates/registry.py`` برای نحوه‌ی تجمیع.
"""

INDUSTRY_TEMPLATES = [
    {
        "slug": "watches", "name": "ساعت و جواهر", "icon": "⌚", "sector": "retail", "version": 1, "display_order": 6,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های ساعت مچی.",
        "categories": [
            {"code": "watches-mens", "name": "ساعت مردانه", "icon": "⌚"},
            {"code": "watches-womens", "name": "ساعت زنانه", "icon": "⌚"},
            {"code": "watches-smart", "name": "ساعت هوشمند", "icon": "📱"},
            {"code": "watches-kids", "name": "ساعت بچگانه", "icon": "🧒"},
        ],
        "attributes": [
            {"code": "watch-brand", "label": "برند", "data_type": "text"},
            {"code": "watch-movement", "label": "نوع موتور", "data_type": "select", "display_type": "dropdown",
             "values": ["کوارتز", "اتوماتیک", "مکانیکی", "دیجیتال"]},
            {"code": "watch-case-material", "label": "جنس بدنه", "data_type": "select", "display_type": "dropdown",
             "values": ["استیل ضدزنگ", "تیتانیوم", "طلا", "پلاستیک", "آلومینیوم"]},
            {"code": "watch-strap-material", "label": "جنس بند", "data_type": "select", "display_type": "dropdown",
             "values": ["چرم", "استیل", "سیلیکونی", "پارچه‌ای"]},
            {"code": "water-resistance", "label": "مقاومت آب", "data_type": "select", "display_type": "dropdown",
             "values": ["ندارد", "۳۰ متر", "۵۰ متر", "۱۰۰ متر", "۲۰۰ متر+"]},
            {"code": "watch-warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "watch-case-size", "label": "قطر بدنه", "data_type": "number", "unit": "میلی‌متر"},
            {"code": "watch-color", "label": "رنگ بند/بدنه", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("طلایی", "#d4af37"), ("نقره‌ای", "#c0c0c0"), ("قهوه‌ای", "#78350f")]},
            {"code": "watch-strap-size", "label": "سایز بند", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["کوچک", "استاندارد", "بزرگ"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": group, "required": required, "filterable": filterable}
            for cat in ("watches-mens", "watches-womens", "watches-smart", "watches-kids")
            for attr, group, required, filterable in [
                ("watch-brand", "عمومی", True, True),
                ("watch-movement", "مشخصات فنی", False, True),
                ("watch-case-material", "مشخصات فنی", False, True),
                ("watch-strap-material", "مشخصات فنی", False, False),
                ("water-resistance", "مشخصات فنی", False, False),
                ("watch-case-size", "ابعاد", False, False),
                ("watch-warranty", "خدمات پس از فروش", False, False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": attr}
            for cat in ("watches-mens", "watches-womens", "watches-smart", "watches-kids")
            for attr in ("watch-color", "watch-strap-size")
        ],
    },
    {
        "slug": "eyewear", "name": "عینک و لوازم شیشه‌ای", "icon": "🕶️", "sector": "retail", "version": 1, "display_order": 7,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های عینک آفتابی و طبی.",
        "categories": [
            {"code": "eyewear-sunglasses", "name": "عینک آفتابی", "icon": "🕶️"},
            {"code": "eyewear-optical", "name": "عینک طبی", "icon": "👓"},
            {"code": "eyewear-lenses", "name": "لنز تماسی", "icon": "👁️"},
            {"code": "eyewear-accessories", "name": "لوازم جانبی عینک", "icon": "🧰"},
        ],
        "attributes": [
            {"code": "eyewear-brand", "label": "برند", "data_type": "text"},
            {"code": "frame-material", "label": "جنس فریم", "data_type": "select", "display_type": "dropdown",
             "values": ["فلزی", "پلاستیکی", "چوبی", "تیتانیومی", "بدون‌فریم"]},
            {"code": "frame-shape", "label": "شکل فریم", "data_type": "select", "display_type": "dropdown",
             "values": ["گرد", "مستطیلی", "گربه‌ای", "هشت‌ضلعی", "بیضی"]},
            {"code": "lens-type", "label": "نوع لنز", "data_type": "select", "display_type": "dropdown",
             "values": ["پلاریزه", "معمولی", "فتوکرومیک", "آینه‌ای"]},
            {"code": "uv-protection", "label": "محافظت UV", "data_type": "boolean"},
            {"code": "eyewear-gender", "label": "جنسیت هدف", "data_type": "select", "display_type": "dropdown",
             "values": ["مردانه", "زنانه", "یونیسکس", "بچگانه"]},
            {"code": "eyewear-color", "label": "رنگ فریم", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("قهوه‌ای", "#78350f"), ("طلایی", "#d4af37"), ("شفاف", "#f3f4f6")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("eyewear-sunglasses", "eyewear-optical")
            for attr, required, filterable in [
                ("eyewear-brand", True, True), ("frame-material", False, True), ("frame-shape", False, True),
                ("lens-type", False, False), ("uv-protection", False, False), ("eyewear-gender", False, True),
            ]
        ] + [
            {"category": "eyewear-lenses", "attribute": "eyewear-brand", "group": "مشخصات", "required": True},
            {"category": "eyewear-accessories", "attribute": "eyewear-brand", "group": "مشخصات"},
        ],
        "recommended_options": [
            {"category": "eyewear-sunglasses", "attribute": "eyewear-color"},
            {"category": "eyewear-optical", "attribute": "eyewear-color"},
        ],
    },
    {
        "slug": "bags-luggage", "name": "کیف و اکسسوری", "icon": "🧳", "sector": "retail", "version": 1, "display_order": 5,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های کیف، کوله و چمدان.",
        "categories": [
            {"code": "bags-handbags", "name": "کیف دستی و رودوشی", "icon": "👜"},
            {"code": "bags-backpacks", "name": "کوله‌پشتی", "icon": "🎒"},
            {"code": "bags-luggage", "name": "چمدان", "icon": "🧳"},
            {"code": "bags-wallets", "name": "کیف پول", "icon": "👛"},
        ],
        "attributes": [
            {"code": "bag-brand", "label": "برند", "data_type": "text"},
            {"code": "bag-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["چرم طبیعی", "چرم مصنوعی", "پارچه‌ای", "نایلونی", "پلی‌کربنات"]},
            {"code": "bag-closure", "label": "نوع بست", "data_type": "select", "display_type": "dropdown",
             "values": ["زیپ‌دار", "دکمه‌ای", "مغناطیسی", "بندی"]},
            {"code": "luggage-hardness", "label": "سختی بدنه (چمدان)", "data_type": "select",
             "display_type": "dropdown", "values": ["سخت", "نیمه‌سخت", "نرم"]},
            {"code": "bag-capacity", "label": "حجم", "data_type": "number", "unit": "لیتر"},
            {"code": "waterproof", "label": "ضدآب", "data_type": "boolean"},
            {"code": "bag-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("قهوه‌ای", "#78350f"), ("قرمز", "#ef4444"), ("بژ", "#e5d3b3")]},
            {"code": "luggage-size", "label": "سایز چمدان", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["کابین", "متوسط", "بزرگ"]},
        ],
        "mappings": [
            {"category": "bags-handbags", "attribute": "bag-brand", "group": "عمومی", "required": True,
             "filterable": True},
            {"category": "bags-handbags", "attribute": "bag-material", "group": "عمومی", "filterable": True},
            {"category": "bags-handbags", "attribute": "bag-closure", "group": "عمومی"},
            {"category": "bags-backpacks", "attribute": "bag-brand", "group": "عمومی", "required": True,
             "filterable": True},
            {"category": "bags-backpacks", "attribute": "bag-material", "group": "عمومی", "filterable": True},
            {"category": "bags-backpacks", "attribute": "bag-capacity", "group": "ابعاد"},
            {"category": "bags-backpacks", "attribute": "waterproof", "group": "ابعاد"},
            {"category": "bags-luggage", "attribute": "bag-brand", "group": "عمومی", "required": True,
             "filterable": True},
            {"category": "bags-luggage", "attribute": "luggage-hardness", "group": "مشخصات", "filterable": True},
            {"category": "bags-luggage", "attribute": "bag-capacity", "group": "ابعاد"},
            {"category": "bags-wallets", "attribute": "bag-brand", "group": "عمومی"},
            {"category": "bags-wallets", "attribute": "bag-material", "group": "عمومی"},
        ],
        "recommended_options": [
            {"category": "bags-handbags", "attribute": "bag-color"},
            {"category": "bags-backpacks", "attribute": "bag-color"},
            {"category": "bags-luggage", "attribute": "bag-color"},
            {"category": "bags-luggage", "attribute": "luggage-size"},
            {"category": "bags-wallets", "attribute": "bag-color"},
        ],
    },
]
