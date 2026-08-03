"""صنایع سلامت و زیبایی (Phase 1F): سلامت شخصی، مراقبت پوست، مو و آرایش."""

INDUSTRY_TEMPLATES = [
    {
        "slug": "health-personal-care", "name": "لوازم بهداشتی", "icon": "🩹", "sector": "beauty", "version": 1, "display_order": 42,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های سلامت و مراقبت شخصی.",
        "categories": [
            {"code": "health-vitamins", "name": "ویتامین و مکمل", "icon": "💊"},
            {"code": "health-oral-care", "name": "بهداشت دهان و دندان", "icon": "🦷"},
            {"code": "health-devices", "name": "تجهیزات پزشکی خانگی", "icon": "🩺"},
            {"code": "health-personal-hygiene", "name": "بهداشت فردی", "icon": "🧼"},
        ],
        "attributes": [
            {"code": "health-brand", "label": "برند", "data_type": "text"},
            {"code": "health-form", "label": "شکل مصرف", "data_type": "select", "display_type": "dropdown",
             "values": ["قرص", "کپسول", "شربت", "پودر", "اسپری", "ژل"]},
            {"code": "health-usage-age", "label": "رده‌ی سنی مصرف", "data_type": "select", "display_type": "dropdown",
             "values": ["کودک", "بزرگسال", "همه‌ی سنین"]},
            {"code": "health-quantity", "label": "تعداد/حجم بسته", "data_type": "text"},
            {"code": "health-country-origin", "label": "کشور سازنده", "data_type": "text"},
            {"code": "prescription-required", "label": "نیاز به نسخه", "data_type": "boolean"},
            {"code": "health-package-size", "label": "اندازه بسته", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["کوچک", "متوسط", "خانواده"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("health-vitamins", "health-oral-care", "health-devices", "health-personal-hygiene")
            for attr, required, filterable in [
                ("health-brand", False, True), ("health-form", False, True), ("health-usage-age", False, True),
                ("health-quantity", False, False), ("prescription-required", False, True),
            ]
        ],
        "recommended_options": [
            {"category": "health-vitamins", "attribute": "health-package-size"},
            {"category": "health-personal-hygiene", "attribute": "health-package-size"},
        ],
    },
    {
        "slug": "skincare", "name": "اسپا و مراقبت پوست", "icon": "🧴", "sector": "beauty", "version": 1, "display_order": 49,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های مراقبت پوست.",
        "categories": [
            {"code": "skincare-cleansers", "name": "شوینده و پاک‌کننده", "icon": "🧼"},
            {"code": "skincare-moisturizers", "name": "مرطوب‌کننده", "icon": "💧"},
            {"code": "skincare-serums", "name": "سرم و درمانی", "icon": "🧪"},
            {"code": "skincare-suncare", "name": "ضدآفتاب", "icon": "☀️"},
            {"code": "skincare-masks", "name": "ماسک صورت", "icon": "🎭"},
        ],
        "attributes": [
            {"code": "skincare-brand", "label": "برند", "data_type": "text"},
            {"code": "skin-type", "label": "نوع پوست", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["چرب", "خشک", "مختلط", "حساس", "معمولی"]},
            {"code": "skincare-concern", "label": "نگرانی پوستی", "data_type": "multiselect",
             "display_type": "checkbox", "values": ["آکنه", "لک", "چروک", "منافذ باز", "کدری"]},
            {"code": "spf-level", "label": "میزان SPF", "data_type": "select", "display_type": "dropdown",
             "values": ["بدون SPF", "SPF 15", "SPF 30", "SPF 50", "SPF 50+"]},
            {"code": "fragrance-free", "label": "بدون رایحه", "data_type": "boolean"},
            {"code": "dermatologist-tested", "label": "تست‌شده توسط متخصص پوست", "data_type": "boolean"},
            {"code": "skincare-volume", "label": "حجم", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["30ml", "50ml", "100ml", "150ml", "200ml"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("skincare-cleansers", "skincare-moisturizers", "skincare-serums", "skincare-masks")
            for attr, required, filterable in [
                ("skincare-brand", True, True), ("skin-type", False, True), ("skincare-concern", False, True),
                ("fragrance-free", False, False), ("dermatologist-tested", False, False),
            ]
        ] + [
            {"category": "skincare-suncare", "attribute": "skincare-brand", "group": "مشخصات", "required": True,
             "filterable": True},
            {"category": "skincare-suncare", "attribute": "spf-level", "group": "مشخصات", "required": True,
             "filterable": True},
            {"category": "skincare-suncare", "attribute": "skin-type", "group": "مشخصات", "filterable": True},
        ],
        "recommended_options": [
            {"category": cat, "attribute": "skincare-volume"}
            for cat in ("skincare-cleansers", "skincare-moisturizers", "skincare-serums", "skincare-suncare")
        ],
    },
    {
        "slug": "haircare", "name": "مراقبت مو", "icon": "💇", "version": 1, "display_order": 19,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های مراقبت مو.",
        "categories": [
            {"code": "haircare-shampoo", "name": "شامپو", "icon": "🧴"},
            {"code": "haircare-conditioner", "name": "نرم‌کننده", "icon": "🧴"},
            {"code": "haircare-styling", "name": "حالت‌دهنده و استایلینگ", "icon": "💈"},
            {"code": "haircare-treatments", "name": "درمان و ترمیم مو", "icon": "🧪"},
            {"code": "haircare-tools", "name": "ابزار آرایش مو", "icon": "🪮"},
        ],
        "attributes": [
            {"code": "haircare-brand", "label": "برند", "data_type": "text"},
            {"code": "hair-type", "label": "نوع مو", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["چرب", "خشک", "معمولی", "فر", "رنگ‌شده", "آسیب‌دیده"]},
            {"code": "sulfate-free", "label": "بدون سولفات", "data_type": "boolean"},
            {"code": "silicone-free", "label": "بدون سیلیکون", "data_type": "boolean"},
            {"code": "haircare-scent", "label": "رایحه", "data_type": "select", "display_type": "dropdown",
             "values": ["بدون رایحه", "میوه‌ای", "گلی", "چوبی"]},
            {"code": "haircare-volume", "label": "حجم", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["200ml", "400ml", "750ml", "1000ml"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("haircare-shampoo", "haircare-conditioner", "haircare-styling", "haircare-treatments")
            for attr, required, filterable in [
                ("haircare-brand", True, True), ("hair-type", False, True), ("sulfate-free", False, True),
                ("silicone-free", False, False), ("haircare-scent", False, False),
            ]
        ] + [
            {"category": "haircare-tools", "attribute": "haircare-brand", "group": "مشخصات", "required": True,
             "filterable": True},
        ],
        "recommended_options": [
            {"category": cat, "attribute": "haircare-volume"}
            for cat in ("haircare-shampoo", "haircare-conditioner")
        ],
    },
    {
        "slug": "makeup", "name": "لوازم آرایشی", "icon": "💋", "sector": "beauty", "version": 1, "display_order": 41,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های لوازم آرایش.",
        "categories": [
            {"code": "makeup-face", "name": "آرایش صورت", "icon": "🎨"},
            {"code": "makeup-eyes", "name": "آرایش چشم", "icon": "👁️"},
            {"code": "makeup-lips", "name": "آرایش لب", "icon": "💄"},
            {"code": "makeup-nails", "name": "لوازم ناخن", "icon": "💅"},
            {"code": "makeup-tools", "name": "ابزار آرایش", "icon": "🖌️"},
        ],
        "attributes": [
            {"code": "makeup-brand", "label": "برند", "data_type": "text"},
            {"code": "makeup-finish", "label": "فینیش", "data_type": "select", "display_type": "dropdown",
             "values": ["مات", "براق", "ساتن", "شبنمی"]},
            {"code": "makeup-coverage", "label": "پوشش", "data_type": "select", "display_type": "dropdown",
             "values": ["سبک", "متوسط", "کامل"]},
            {"code": "cruelty-free", "label": "بدون آزمایش حیوانی", "data_type": "boolean"},
            {"code": "waterproof-makeup", "label": "ضدآب", "data_type": "boolean"},
            {"code": "makeup-shade", "label": "شید/رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("بژ روشن", "#f3d5b5"), ("بژ متوسط", "#e0ac69"), ("بژ تیره", "#8d5524"),
                        ("قرمز", "#ef4444"), ("صورتی", "#f472b6")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required, "filterable": filterable}
            for cat in ("makeup-face", "makeup-eyes", "makeup-lips", "makeup-nails")
            for attr, required, filterable in [
                ("makeup-brand", True, True), ("makeup-finish", False, True), ("makeup-coverage", False, False),
                ("cruelty-free", False, True), ("waterproof-makeup", False, False),
            ]
        ] + [
            {"category": "makeup-tools", "attribute": "makeup-brand", "group": "مشخصات", "filterable": True},
        ],
        "recommended_options": [
            {"category": cat, "attribute": "makeup-shade"}
            for cat in ("makeup-face", "makeup-eyes", "makeup-lips", "makeup-nails")
        ],
    },
]
