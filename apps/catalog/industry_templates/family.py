"""صنایع خانواده/کودک/ورزش (Phase 1F): اسباب‌بازی، نوزاد، ورزش و تناسب‌اندام."""

INDUSTRY_TEMPLATES = [
    {
        "slug": "toys-children", "name": "اسباب‌بازی و کودک", "icon": "🧸", "version": 1, "display_order": 14,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های اسباب‌بازی و لوازم کودک.",
        "categories": [
            {"code": "toys-educational", "name": "اسباب‌بازی آموزشی", "icon": "🧩"},
            {"code": "toys-dolls-figures", "name": "عروسک و فیگور", "icon": "🪆"},
            {"code": "toys-outdoor", "name": "اسباب‌بازی فضای باز", "icon": "🚲"},
            {"code": "toys-games", "name": "بازی فکری", "icon": "🎲"},
            {"code": "toys-remote-control", "name": "کنترلی و رباتیک", "icon": "🚗"},
        ],
        "attributes": [
            {"code": "toy-brand", "label": "برند", "data_type": "text"},
            {"code": "toy-age-range", "label": "رده‌ی سنی", "data_type": "select", "display_type": "dropdown",
             "values": ["۰ تا ۲ سال", "۳ تا ۵ سال", "۶ تا ۹ سال", "۱۰ سال به بالا"]},
            {"code": "toy-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["پلاستیکی", "چوبی", "پارچه‌ای", "فلزی"]},
            {"code": "battery-required", "label": "نیاز به باتری", "data_type": "boolean"},
            {"code": "toy-safety-standard", "label": "استاندارد ایمنی", "data_type": "text"},
            {"code": "toy-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("قرمز", "#ef4444"), ("آبی", "#3b82f6"), ("زرد", "#eab308"), ("سبز", "#22c55e")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("toys-educational", "toys-dolls-figures", "toys-outdoor", "toys-games", "toys-remote-control")
            for attr, required, filterable in [
                ("toy-brand", False, True), ("toy-age-range", True, True), ("toy-material", False, True),
                ("battery-required", False, False), ("toy-safety-standard", False, False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": "toy-color"}
            for cat in ("toys-educational", "toys-dolls-figures", "toys-outdoor")
        ],
    },
    {
        "slug": "baby-products", "name": "لوازم نوزاد و کودک", "icon": "🍼", "version": 1, "display_order": 15,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های لوازم نوزاد.",
        "categories": [
            {"code": "baby-feeding", "name": "لوازم تغذیه", "icon": "🍼"},
            {"code": "baby-diapering", "name": "لوازم بهداشتی و پوشک", "icon": "🧷"},
            {"code": "baby-gear", "name": "کالسکه و صندلی خودرو", "icon": "🚼"},
            {"code": "baby-clothing", "name": "پوشاک نوزاد", "icon": "👶"},
            {"code": "baby-nursery", "name": "اتاق و خواب نوزاد", "icon": "🛏️"},
        ],
        "attributes": [
            {"code": "baby-brand", "label": "برند", "data_type": "text"},
            {"code": "baby-age-range", "label": "رده‌ی سنی", "data_type": "select", "display_type": "dropdown",
             "values": ["۰ تا ۶ ماه", "۶ تا ۱۲ ماه", "۱ تا ۲ سال", "۲ تا ۴ سال"]},
            {"code": "baby-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["نخی ارگانیک", "پلاستیک بدون BPA", "سیلیکونی", "پارچه‌ای"]},
            {"code": "bpa-free", "label": "بدون BPA", "data_type": "boolean"},
            {"code": "baby-safety-certified", "label": "دارای گواهی ایمنی", "data_type": "boolean"},
            {"code": "baby-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["نوزاد", "۳-۶ ماه", "۶-۹ ماه", "۹-۱۲ ماه", "۱۲-۱۸ ماه"]},
            {"code": "baby-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("صورتی", "#f9a8d4"), ("آبی روشن", "#93c5fd"), ("زرد", "#fde68a"), ("سفید", "#f9fafb")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("baby-feeding", "baby-diapering", "baby-gear", "baby-clothing", "baby-nursery")
            for attr, required, filterable in [
                ("baby-brand", False, True), ("baby-age-range", True, True), ("baby-material", False, True),
                ("baby-safety-certified", False, False),
            ]
        ] + [
            {"category": "baby-feeding", "attribute": "bpa-free", "group": "ایمنی"},
            {"category": "baby-gear", "attribute": "bpa-free", "group": "ایمنی"},
        ],
        "recommended_options": [
            {"category": "baby-clothing", "attribute": "baby-size"},
            {"category": "baby-clothing", "attribute": "baby-color"},
            {"category": "baby-nursery", "attribute": "baby-color"},
        ],
    },
    {
        "slug": "sports-fitness", "name": "ورزش و تناسب‌اندام", "icon": "🏋️", "version": 1, "display_order": 16,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های ورزشی و تناسب‌اندام.",
        "categories": [
            {"code": "sports-fitness-equipment", "name": "تجهیزات بدنسازی", "icon": "🏋️"},
            {"code": "sports-apparel", "name": "پوشاک ورزشی", "icon": "🩳"},
            {"code": "sports-outdoor", "name": "ورزش‌های فضای باز", "icon": "🏕️"},
            {"code": "sports-team", "name": "ورزش‌های تیمی", "icon": "⚽"},
            {"code": "sports-nutrition", "name": "مکمل و تغذیه‌ی ورزشی", "icon": "🥤"},
        ],
        "attributes": [
            {"code": "sport-brand", "label": "برند", "data_type": "text"},
            {"code": "sport-type", "label": "رشته‌ی ورزشی", "data_type": "select", "display_type": "dropdown",
             "values": ["دویدن", "یوگا", "بدنسازی", "فوتبال", "بسکتبال", "کوهنوردی", "شنا"]},
            {"code": "sport-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["پلی‌استر", "نخی", "نئوپرن", "فلزی", "لاستیکی"]},
            {"code": "sport-gender", "label": "جنسیت هدف", "data_type": "select", "display_type": "dropdown",
             "values": ["مردانه", "زنانه", "یونیسکس"]},
            {"code": "weight-capacity-sport", "label": "وزن قابل تحمل", "data_type": "number", "unit": "کیلوگرم"},
            {"code": "sport-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["S", "M", "L", "XL", "XXL"]},
            {"code": "sport-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("آبی", "#3b82f6"), ("قرمز", "#ef4444"), ("طوسی", "#6b7280")]},
        ],
        "mappings": [
            {"category": "sports-fitness-equipment", "attribute": "sport-brand", "group": "عمومی",
             "filterable": True},
            {"category": "sports-fitness-equipment", "attribute": "sport-material", "group": "عمومی",
             "filterable": True},
            {"category": "sports-fitness-equipment", "attribute": "weight-capacity-sport", "group": "مشخصات"},
            {"category": "sports-apparel", "attribute": "sport-brand", "group": "عمومی", "filterable": True},
            {"category": "sports-apparel", "attribute": "sport-type", "group": "عمومی", "filterable": True},
            {"category": "sports-apparel", "attribute": "sport-gender", "group": "عمومی", "filterable": True},
            {"category": "sports-outdoor", "attribute": "sport-brand", "group": "عمومی"},
            {"category": "sports-outdoor", "attribute": "sport-type", "group": "عمومی", "filterable": True},
            {"category": "sports-team", "attribute": "sport-brand", "group": "عمومی"},
            {"category": "sports-team", "attribute": "sport-type", "group": "عمومی", "required": True,
             "filterable": True},
            {"category": "sports-nutrition", "attribute": "sport-brand", "group": "عمومی", "required": True},
        ],
        "recommended_options": [
            {"category": "sports-apparel", "attribute": "sport-size"},
            {"category": "sports-apparel", "attribute": "sport-color"},
            {"category": "sports-team", "attribute": "sport-size"},
        ],
    },
]
