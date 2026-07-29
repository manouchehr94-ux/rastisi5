"""صنایع سبک زندگی (Phase 1F): گل و هدیه، محصولات دیجیتال/نرم‌افزار، آلات موسیقی."""

INDUSTRY_TEMPLATES = [
    {
        "slug": "flowers-gifts", "name": "گل و هدیه", "icon": "💐", "version": 1, "display_order": 28,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های گل‌فروشی و هدیه.",
        "categories": [
            {"code": "flowers-bouquets", "name": "دسته‌گل", "icon": "💐"},
            {"code": "flowers-arrangements", "name": "سبد و آرایش گل", "icon": "🧺"},
            {"code": "gifts-boxes", "name": "باکس هدیه", "icon": "🎁"},
            {"code": "gifts-plants", "name": "گل و گیاه آپارتمانی", "icon": "🪴"},
        ],
        "attributes": [
            {"code": "flower-type", "label": "نوع گل", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["رز", "لیلیوم", "ارکیده", "آفتابگردان", "میکس"]},
            {"code": "occasion", "label": "مناسبت", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["تولد", "عروسی", "سالگرد", "تسلیت", "تبریک"]},
            {"code": "gift-includes-card", "label": "همراه با کارت تبریک", "data_type": "boolean"},
            {"code": "same-day-delivery", "label": "ارسال همان‌روز", "data_type": "boolean"},
            {"code": "gift-size", "label": "اندازه", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["کوچک", "متوسط", "بزرگ", "لوکس"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("flowers-bouquets", "flowers-arrangements", "gifts-boxes")
            for attr, required, filterable in [
                ("flower-type", False, True), ("occasion", True, True), ("gift-includes-card", False, False),
                ("same-day-delivery", False, True),
            ]
        ] + [
            {"category": "gifts-plants", "attribute": "occasion", "group": "مشخصات", "filterable": True},
        ],
        "recommended_options": [
            {"category": "flowers-bouquets", "attribute": "gift-size"},
            {"category": "gifts-boxes", "attribute": "gift-size"},
        ],
    },
    {
        "slug": "digital-products-software", "name": "محصولات دیجیتال و نرم‌افزار", "icon": "💾", "version": 1,
        "display_order": 29,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های محصولات دیجیتال، نرم‌افزار و لایسنس.",
        "categories": [
            {"code": "digital-software-licenses", "name": "لایسنس نرم‌افزار", "icon": "🔑"},
            {"code": "digital-ebooks-courses", "name": "کتاب و دوره‌ی الکترونیکی", "icon": "📖"},
            {"code": "digital-game-codes", "name": "کد بازی و اشتراک", "icon": "🎮"},
            {"code": "digital-templates-assets", "name": "قالب و فایل آماده", "icon": "🎨"},
        ],
        "attributes": [
            {"code": "digital-publisher", "label": "ناشر/سازنده", "data_type": "text"},
            {"code": "delivery-method", "label": "روش تحویل", "data_type": "select", "display_type": "dropdown",
             "values": ["کد فعال‌سازی ایمیلی", "دانلود مستقیم", "لایسنس آنلاین"]},
            {"code": "platform-compatibility", "label": "سازگاری با پلتفرم", "data_type": "multiselect",
             "display_type": "checkbox", "values": ["ویندوز", "macOS", "لینوکس", "اندروید", "iOS", "وب"]},
            {"code": "license-duration", "label": "مدت اعتبار لایسنس", "data_type": "select",
             "display_type": "dropdown", "values": ["یک‌ماهه", "یک‌ساله", "مادام‌العمر"]},
            {"code": "digital-language", "label": "زبان محتوا", "data_type": "select", "display_type": "dropdown",
             "values": ["فارسی", "انگلیسی", "چندزبانه"]},
            {"code": "refundable-digital", "label": "قابل استرداد", "data_type": "boolean"},
        ],
        "mappings": [
            {"category": "digital-software-licenses", "attribute": "digital-publisher", "group": "مشخصات",
             "required": True, "filterable": True},
            {"category": "digital-software-licenses", "attribute": "delivery-method", "group": "مشخصات",
             "required": True, "filterable": True},
            {"category": "digital-software-licenses", "attribute": "platform-compatibility", "group": "مشخصات",
             "filterable": True},
            {"category": "digital-software-licenses", "attribute": "license-duration", "group": "مشخصات",
             "filterable": True},
            {"category": "digital-ebooks-courses", "attribute": "digital-publisher", "group": "مشخصات",
             "filterable": True},
            {"category": "digital-ebooks-courses", "attribute": "digital-language", "group": "مشخصات",
             "filterable": True},
            {"category": "digital-game-codes", "attribute": "delivery-method", "group": "مشخصات", "required": True,
             "filterable": True},
            {"category": "digital-game-codes", "attribute": "platform-compatibility", "group": "مشخصات",
             "filterable": True},
            {"category": "digital-templates-assets", "attribute": "delivery-method", "group": "مشخصات",
             "required": True},
        ],
        "recommended_options": [],
    },
    {
        "slug": "musical-instruments", "name": "آلات موسیقی", "icon": "🎸", "version": 1, "display_order": 30,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های آلات و لوازم موسیقی.",
        "categories": [
            {"code": "music-string", "name": "سازهای زهی", "icon": "🎸"},
            {"code": "music-keyboard", "name": "سازهای کیبوردی", "icon": "🎹"},
            {"code": "music-percussion", "name": "سازهای کوبه‌ای", "icon": "🥁"},
            {"code": "music-wind", "name": "سازهای بادی", "icon": "🎷"},
            {"code": "music-accessories", "name": "لوازم جانبی موسیقی", "icon": "🎼"},
        ],
        "attributes": [
            {"code": "instrument-brand", "label": "برند", "data_type": "text"},
            {"code": "instrument-level", "label": "سطح مهارت", "data_type": "select", "display_type": "dropdown",
             "values": ["مبتدی", "متوسط", "حرفه‌ای"]},
            {"code": "instrument-material", "label": "جنس بدنه", "data_type": "select", "display_type": "dropdown",
             "values": ["چوب ماهون", "چوب افرا", "فلزی", "کامپوزیت"]},
            {"code": "is-electric", "label": "برقی/الکتریک", "data_type": "boolean"},
            {"code": "number-of-keys-strings", "label": "تعداد کلید/سیم", "data_type": "number"},
            {"code": "instrument-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("طبیعی چوب", "#a0522d"), ("مشکی", "#111827"), ("قرمز سان‌برست", "#b91c1c"),
                        ("سفید", "#f9fafb")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("music-string", "music-keyboard", "music-percussion", "music-wind")
            for attr, required, filterable in [
                ("instrument-brand", False, True), ("instrument-level", True, True),
                ("instrument-material", False, True),
            ]
        ] + [
            {"category": "music-keyboard", "attribute": "is-electric", "group": "مشخصات", "filterable": True},
            {"category": "music-keyboard", "attribute": "number-of-keys-strings", "group": "مشخصات فنی"},
            {"category": "music-string", "attribute": "number-of-keys-strings", "group": "مشخصات فنی"},
            {"category": "music-accessories", "attribute": "instrument-brand", "group": "مشخصات",
             "filterable": True},
        ],
        "recommended_options": [
            {"category": "music-string", "attribute": "instrument-color"},
            {"category": "music-keyboard", "attribute": "instrument-color"},
        ],
    },
]
