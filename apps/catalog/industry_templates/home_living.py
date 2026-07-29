"""صنایع خانه و زندگی (Phase 1F): ظروف آشپزخانه، رختخواب/حمام، لوازم حیوانات خانگی."""

INDUSTRY_TEMPLATES = [
    {
        "slug": "kitchenware", "name": "ظروف و لوازم آشپزخانه", "icon": "🍳", "version": 1, "display_order": 25,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های ظروف و لوازم آشپزخانه.",
        "categories": [
            {"code": "kitchenware-cookware", "name": "قابلمه و تابه", "icon": "🍳"},
            {"code": "kitchenware-cutlery", "name": "کارد و چنگال", "icon": "🍴"},
            {"code": "kitchenware-storage", "name": "ظروف نگهداری", "icon": "🥡"},
            {"code": "kitchenware-bakeware", "name": "لوازم پخت و قنادی", "icon": "🧁"},
            {"code": "kitchenware-small-appliances", "name": "لوازم برقی کوچک آشپزخانه", "icon": "🔌"},
        ],
        "attributes": [
            {"code": "kitchen-brand", "label": "برند", "data_type": "text"},
            {"code": "kitchen-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["استیل ضدزنگ", "چدن", "تفلون (نچسب)", "شیشه‌ای", "سرامیکی", "پلاستیکی"]},
            {"code": "dishwasher-safe", "label": "مناسب ماشین ظرفشویی", "data_type": "boolean"},
            {"code": "induction-compatible", "label": "مناسب اجاق القایی", "data_type": "boolean"},
            {"code": "kitchen-piece-count", "label": "تعداد قطعات ست", "data_type": "number"},
            {"code": "kitchen-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("سفید", "#f9fafb"), ("قرمز", "#ef4444"), ("نقره‌ای", "#9ca3af")]},
            {"code": "kitchen-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["کوچک", "متوسط", "بزرگ"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("kitchenware-cookware", "kitchenware-cutlery", "kitchenware-storage",
                        "kitchenware-bakeware")
            for attr, required, filterable in [
                ("kitchen-brand", False, True), ("kitchen-material", True, True),
                ("dishwasher-safe", False, True), ("induction-compatible", False, False),
            ]
        ] + [
            {"category": "kitchenware-small-appliances", "attribute": "kitchen-brand", "group": "مشخصات",
             "required": True, "filterable": True},
        ],
        "recommended_options": [
            {"category": "kitchenware-cookware", "attribute": "kitchen-color"},
            {"category": "kitchenware-cookware", "attribute": "kitchen-size"},
            {"category": "kitchenware-storage", "attribute": "kitchen-size"},
        ],
    },
    {
        "slug": "bedding-bath", "name": "رختخواب و حمام", "icon": "🛁", "version": 1, "display_order": 26,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های سرویس‌خواب و لوازم حمام.",
        "categories": [
            {"code": "bedding-sheets", "name": "ملحفه و روتختی", "icon": "🛏️"},
            {"code": "bedding-pillows-duvets", "name": "بالش و لحاف", "icon": "🛌"},
            {"code": "bath-towels", "name": "حوله", "icon": "🧻"},
            {"code": "bath-accessories", "name": "لوازم جانبی حمام", "icon": "🚿"},
        ],
        "attributes": [
            {"code": "textile-brand", "label": "برند", "data_type": "text"},
            {"code": "textile-material", "label": "جنس پارچه", "data_type": "select", "display_type": "dropdown",
             "values": ["پنبه ۱۰۰٪", "میکروفایبر", "ساتن", "کتان", "پلی‌استر"]},
            {"code": "thread-count", "label": "تراکم بافت (Thread Count)", "data_type": "number"},
            {"code": "bed-size", "label": "سایز تخت", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["یک‌نفره", "دونفره", "کینگ‌سایز"]},
            {"code": "textile-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("سفید", "#f9fafb"), ("طوسی", "#9ca3af"), ("آبی", "#3b82f6"), ("بژ", "#e5d3b3")]},
            {"code": "hypoallergenic", "label": "ضدحساسیت", "data_type": "boolean"},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("bedding-sheets", "bedding-pillows-duvets", "bath-towels")
            for attr, required, filterable in [
                ("textile-brand", False, True), ("textile-material", True, True),
                ("thread-count", False, False), ("hypoallergenic", False, False),
            ]
        ] + [
            {"category": "bath-accessories", "attribute": "textile-brand", "group": "مشخصات", "filterable": True},
        ],
        "recommended_options": [
            {"category": "bedding-sheets", "attribute": "bed-size"},
            {"category": "bedding-sheets", "attribute": "textile-color"},
            {"category": "bedding-pillows-duvets", "attribute": "bed-size"},
            {"category": "bath-towels", "attribute": "textile-color"},
        ],
    },
    {
        "slug": "pet-supplies", "name": "لوازم حیوانات خانگی", "icon": "🐾", "version": 1, "display_order": 27,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های لوازم حیوانات خانگی.",
        "categories": [
            {"code": "pet-food", "name": "غذای حیوانات", "icon": "🥫"},
            {"code": "pet-toys", "name": "اسباب‌بازی حیوانات", "icon": "🎾"},
            {"code": "pet-grooming", "name": "بهداشت و نظافت حیوانات", "icon": "🧴"},
            {"code": "pet-accessories", "name": "لوازم جانبی و قفس", "icon": "🐕"},
        ],
        "attributes": [
            {"code": "pet-brand", "label": "برند", "data_type": "text"},
            {"code": "pet-species", "label": "نوع حیوان", "data_type": "select", "display_type": "dropdown",
             "values": ["سگ", "گربه", "پرنده", "ماهی", "جونده"]},
            {"code": "pet-age-stage", "label": "مرحله‌ی سنی", "data_type": "select", "display_type": "dropdown",
             "values": ["توله/بچه", "بزرگسال", "سالمند"]},
            {"code": "pet-food-flavor", "label": "طعم", "data_type": "select", "display_type": "dropdown",
             "values": ["مرغ", "گوشت گاو", "ماهی", "بره", "میکس سبزیجات"]},
            {"code": "pet-weight-range", "label": "رده‌ی وزنی نژاد", "data_type": "select", "display_type": "dropdown",
             "values": ["نژاد کوچک", "نژاد متوسط", "نژاد بزرگ"]},
            {"code": "pet-package-size", "label": "وزن بسته", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["1کیلوگرم", "3کیلوگرم", "10کیلوگرم", "15کیلوگرم"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("pet-food", "pet-toys", "pet-grooming", "pet-accessories")
            for attr, required, filterable in [
                ("pet-brand", False, True), ("pet-species", True, True), ("pet-age-stage", False, True),
            ]
        ] + [
            {"category": "pet-food", "attribute": "pet-food-flavor", "group": "مشخصات", "filterable": True},
            {"category": "pet-food", "attribute": "pet-weight-range", "group": "مشخصات", "filterable": True},
        ],
        "recommended_options": [
            {"category": "pet-food", "attribute": "pet-package-size"},
        ],
    },
]
