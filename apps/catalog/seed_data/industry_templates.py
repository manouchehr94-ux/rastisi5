"""داده‌ی نسخه‌بندی‌شده‌ی قالب‌های صنف اولیه — نگاه کنید به ADR-25.

هر ورودی این فهرست دقیقاً به یک ``IndustryTemplate`` (با ``version`` مشخص)
نگاشت می‌شود. این فایل فقط داده است — منطق ساخت رکورد در
``apps.catalog.management.commands.seed_industry_templates`` است، تا داده
و کد اجرا کاملاً جدا بمانند (به همان روحیه‌ی migration دیتاِ پروژه).

هر ویژگیِ ``data_type`` از نوع ``select``/``multiselect``/``color`` باید
``values`` داشته باشد؛ مقادیر رنگ به‌صورت ``(label, hex)`` نوشته می‌شوند،
بقیه فقط برچسب ساده‌اند. ``mappings`` نگاشت ویژگی توصیفی به دسته‌بندی
(معمولاً روی دسته‌ی سطح‌بالا، تا با ارث‌بری به زیردسته‌ها هم برسد) و
``recommended_options`` محورهای تنوع پیشنهادی (فقط ویژگی‌های
``is_variant_axis=True``) را مشخص می‌کند.
"""

INDUSTRY_TEMPLATES = [
    {
        "slug": "clothing-fashion", "name": "پوشاک و مد", "icon": "👕", "version": 1, "display_order": 1,
        "description": "دسته‌بندی، ویژگی‌های توصیفی و محورهای تنوع استاندارد برای فروشگاه‌های پوشاک.",
        "categories": [
            {"code": "clothing", "name": "پوشاک", "icon": "👕", "children": [
                {"code": "clothing-mens", "name": "مردانه", "icon": "👔", "children": [
                    {"code": "clothing-mens-tshirts", "name": "تی‌شرت و پلوشرت", "icon": "👕"},
                    {"code": "clothing-mens-shirts", "name": "پیراهن", "icon": "👔"},
                    {"code": "clothing-mens-pants", "name": "شلوار", "icon": "👖"},
                ]},
                {"code": "clothing-womens", "name": "زنانه", "icon": "👗"},
                {"code": "clothing-kids", "name": "بچگانه", "icon": "🧒"},
                {"code": "clothing-accessories", "name": "اکسسوری پوشاک", "icon": "🧣"},
            ]},
        ],
        "attributes": [
            {"code": "material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["نخی", "پلی‌استر", "کتان", "دنیم", "پشمی", "چرم"]},
            {"code": "fit", "label": "فیت", "data_type": "select", "display_type": "dropdown",
             "values": ["اسلیم", "معمولی", "ریلکس", "اورسایز"]},
            {"code": "season", "label": "فصل مناسب", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["بهار", "تابستان", "پاییز", "زمستان"]},
            {"code": "pattern", "label": "طرح", "data_type": "select", "display_type": "dropdown",
             "values": ["ساده", "راه‌راه", "چهارخانه", "چاپی"]},
            {"code": "sleeve-type", "label": "نوع آستین", "data_type": "select", "display_type": "dropdown",
             "values": ["آستین‌کوتاه", "آستین‌بلند", "بدون‌آستین"]},
            {"code": "care-instructions", "label": "دستور شست‌وشو", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
            {"code": "clothing-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("سبز", "#22c55e"), ("آبی", "#3b82f6"), ("قرمز", "#ef4444"), ("مشکی", "#111827"), ("سفید", "#f9fafb")]},
            {"code": "clothing-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["S", "M", "L", "XL", "XXL"]},
        ],
        "mappings": [
            {"category": "clothing-mens", "attribute": "material", "group": "عمومی", "required": True},
            {"category": "clothing-mens", "attribute": "fit", "group": "عمومی"},
            {"category": "clothing-mens", "attribute": "season", "group": "عمومی"},
            {"category": "clothing-mens", "attribute": "pattern", "group": "عمومی"},
            {"category": "clothing-mens", "attribute": "sleeve-type", "group": "عمومی"},
            {"category": "clothing-mens", "attribute": "care-instructions", "group": "مراقبت و نگهداری"},
            {"category": "clothing-mens", "attribute": "origin-country", "group": "مراقبت و نگهداری"},
            {"category": "clothing-womens", "attribute": "material", "group": "عمومی", "required": True},
            {"category": "clothing-womens", "attribute": "fit", "group": "عمومی"},
            {"category": "clothing-womens", "attribute": "season", "group": "عمومی"},
            {"category": "clothing-womens", "attribute": "pattern", "group": "عمومی"},
            {"category": "clothing-womens", "attribute": "care-instructions", "group": "مراقبت و نگهداری"},
            {"category": "clothing-kids", "attribute": "material", "group": "عمومی", "required": True},
            {"category": "clothing-kids", "attribute": "season", "group": "عمومی"},
            {"category": "clothing-kids", "attribute": "care-instructions", "group": "مراقبت و نگهداری"},
        ],
        "recommended_options": [
            {"category": "clothing-mens", "attribute": "clothing-color"},
            {"category": "clothing-mens", "attribute": "clothing-size"},
            {"category": "clothing-womens", "attribute": "clothing-color"},
            {"category": "clothing-womens", "attribute": "clothing-size"},
            {"category": "clothing-kids", "attribute": "clothing-color"},
            {"category": "clothing-kids", "attribute": "clothing-size"},
        ],
    },
    {
        "slug": "shoes", "name": "کفش و چرم", "icon": "👟", "sector": "retail", "version": 1, "display_order": 4,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های کفش.",
        "categories": [
            {"code": "shoes-mens", "name": "کفش مردانه", "icon": "👞"},
            {"code": "shoes-womens", "name": "کفش زنانه", "icon": "👠"},
            {"code": "shoes-kids", "name": "کفش بچگانه", "icon": "👟"},
            {"code": "shoes-sport", "name": "کفش ورزشی", "icon": "🏃"},
        ],
        "attributes": [
            {"code": "upper-material", "label": "جنس رویه", "data_type": "select", "display_type": "dropdown",
             "values": ["چرم طبیعی", "چرم مصنوعی", "پارچه‌ای", "مش"]},
            {"code": "closure-type", "label": "نوع بند", "data_type": "select", "display_type": "dropdown",
             "values": ["بندی", "چسبی", "کشی", "زیپ‌دار"]},
            {"code": "usage", "label": "کاربری", "data_type": "select", "display_type": "dropdown",
             "values": ["روزمره", "ورزشی", "رسمی", "کوهنوردی"]},
            {"code": "heel-height", "label": "ارتفاع پاشنه", "data_type": "number", "unit": "سانتی‌متر"},
            {"code": "shoes-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("قهوه‌ای", "#78350f"), ("سفید", "#f9fafb"), ("سرمه‌ای", "#1e3a8a")]},
            {"code": "shoes-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": [str(n) for n in range(36, 46)]},
        ],
        "mappings": [
            {"category": "shoes-mens", "attribute": "upper-material", "group": "مشخصات", "required": True},
            {"category": "shoes-mens", "attribute": "closure-type", "group": "مشخصات"},
            {"category": "shoes-mens", "attribute": "usage", "group": "مشخصات"},
            {"category": "shoes-mens", "attribute": "heel-height", "group": "ابعاد"},
            {"category": "shoes-womens", "attribute": "upper-material", "group": "مشخصات", "required": True},
            {"category": "shoes-womens", "attribute": "closure-type", "group": "مشخصات"},
            {"category": "shoes-womens", "attribute": "usage", "group": "مشخصات"},
            {"category": "shoes-womens", "attribute": "heel-height", "group": "ابعاد"},
            {"category": "shoes-kids", "attribute": "upper-material", "group": "مشخصات"},
            {"category": "shoes-kids", "attribute": "usage", "group": "مشخصات"},
            {"category": "shoes-sport", "attribute": "upper-material", "group": "مشخصات"},
            {"category": "shoes-sport", "attribute": "usage", "group": "مشخصات", "required": True},
        ],
        "recommended_options": [
            {"category": "shoes-mens", "attribute": "shoes-color"},
            {"category": "shoes-mens", "attribute": "shoes-size"},
            {"category": "shoes-womens", "attribute": "shoes-color"},
            {"category": "shoes-womens", "attribute": "shoes-size"},
            {"category": "shoes-kids", "attribute": "shoes-color"},
            {"category": "shoes-kids", "attribute": "shoes-size"},
            {"category": "shoes-sport", "attribute": "shoes-color"},
            {"category": "shoes-sport", "attribute": "shoes-size"},
        ],
    },
    {
        "slug": "perfume-cosmetics", "name": "عطر و ادکلن", "icon": "💄", "sector": "beauty", "version": 1, "display_order": 43,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های عطر و لوازم آرایشی.",
        "categories": [
            {"code": "perfume-mens", "name": "عطر مردانه", "icon": "🧴"},
            {"code": "perfume-womens", "name": "عطر زنانه", "icon": "🌸"},
            {"code": "perfume-unisex", "name": "عطر یونیسکس", "icon": "🧴"},
            {"code": "perfume-giftsets", "name": "ست هدیه", "icon": "🎁"},
            {"code": "perfume-bodyspray", "name": "اسپری بدن", "icon": "💦"},
        ],
        "attributes": [
            {"code": "perfume-brand", "label": "برند", "data_type": "text"},
            {"code": "fragrance-family", "label": "خانواده رایحه", "data_type": "select", "display_type": "dropdown",
             "values": ["شرقی", "چوبی", "گلی", "مرکباتی", "ادویه‌ای", "آروماتیک"]},
            {"code": "top-notes", "label": "نت‌های اولیه", "data_type": "text"},
            {"code": "middle-notes", "label": "نت‌های میانی", "data_type": "text"},
            {"code": "base-notes", "label": "نت‌های پایه", "data_type": "text"},
            {"code": "concentration", "label": "غلظت", "data_type": "select", "display_type": "dropdown",
             "values": ["ادوکلن (EDC)", "ادوتویلت (EDT)", "ادوپرفیوم (EDP)", "پرفیوم (Parfum)"]},
            {"code": "perfume-season", "label": "فصل مناسب", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["بهار", "تابستان", "پاییز", "زمستان"]},
            {"code": "longevity", "label": "ماندگاری", "data_type": "select", "display_type": "dropdown",
             "values": ["کم (۲-۳ ساعت)", "متوسط (۴-۶ ساعت)", "زیاد (۷-۱۰ ساعت)", "خیلی‌زیاد (+۱۰ ساعت)"]},
            {"code": "sillage", "label": "پخش رایحه (سیلاژ)", "data_type": "select", "display_type": "dropdown",
             "values": ["ملایم", "متوسط", "قوی"]},
            {"code": "perfume-origin", "label": "کشور سازنده", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["30ml", "50ml", "75ml", "100ml", "125ml"]},
            {"code": "package-type", "label": "نوع بسته‌بندی", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["جعبه‌دار", "بدون‌جعبه", "تستر"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": group, "required": required}
            for cat in ("perfume-mens", "perfume-womens", "perfume-unisex", "perfume-giftsets", "perfume-bodyspray")
            for attr, group, required in [
                ("perfume-brand", "عمومی", True),
                ("fragrance-family", "عمومی", True),
                ("top-notes", "نت‌های رایحه", False),
                ("middle-notes", "نت‌های رایحه", False),
                ("base-notes", "نت‌های رایحه", False),
                ("concentration", "مشخصات", False),
                ("perfume-season", "مشخصات", False),
                ("longevity", "مشخصات", False),
                ("sillage", "مشخصات", False),
                ("perfume-origin", "مشخصات", False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": attr}
            for cat in ("perfume-mens", "perfume-womens", "perfume-unisex", "perfume-giftsets", "perfume-bodyspray")
            for attr in ("volume", "package-type")
        ],
    },
    {
        "slug": "mobile-phones", "name": "موبایل و تبلت", "icon": "📱", "sector": "digital", "version": 1, "display_order": 11,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های موبایل و تبلت.",
        "categories": [
            {"code": "mobile-phones", "name": "گوشی موبایل", "icon": "📱"},
            {"code": "mobile-tablets", "name": "تبلت", "icon": "📲"},
            {"code": "mobile-accessories", "name": "لوازم جانبی موبایل", "icon": "🎧"},
        ],
        "attributes": [
            {"code": "mobile-brand", "label": "برند", "data_type": "select", "display_type": "dropdown",
             "values": ["سامسونگ", "اپل", "شیائومی", "هوآوی", "نوکیا", "سایر"]},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "chipset", "label": "چیپست", "data_type": "text"},
            {"code": "screen-size", "label": "اندازه صفحه‌نمایش", "data_type": "number", "unit": "اینچ"},
            {"code": "battery-capacity", "label": "ظرفیت باتری", "data_type": "number", "unit": "میلی‌آمپرساعت"},
            {"code": "camera", "label": "دوربین", "data_type": "text"},
            {"code": "network", "label": "شبکه", "data_type": "select", "display_type": "dropdown",
             "values": ["3G", "4G", "5G"]},
            {"code": "os", "label": "سیستم‌عامل", "data_type": "select", "display_type": "dropdown",
             "values": ["اندروید", "iOS", "سایر"]},
            {"code": "mobile-warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "mobile-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("نقره‌ای", "#9ca3af"), ("طلایی", "#d4af37"), ("آبی", "#3b82f6")]},
            {"code": "storage", "label": "حافظه داخلی", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["64GB", "128GB", "256GB", "512GB", "1TB"]},
            {"code": "ram", "label": "رم", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["4GB", "6GB", "8GB", "12GB", "16GB"]},
        ],
        "mappings": [
            {"category": "mobile-phones", "attribute": "mobile-brand", "group": "عمومی", "required": True},
            {"category": "mobile-phones", "attribute": "model", "group": "عمومی", "required": True},
            {"category": "mobile-phones", "attribute": "chipset", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "screen-size", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "battery-capacity", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "camera", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "network", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "os", "group": "فنی"},
            {"category": "mobile-phones", "attribute": "mobile-warranty", "group": "خدمات پس از فروش"},
            {"category": "mobile-tablets", "attribute": "mobile-brand", "group": "عمومی", "required": True},
            {"category": "mobile-tablets", "attribute": "screen-size", "group": "فنی"},
            {"category": "mobile-tablets", "attribute": "battery-capacity", "group": "فنی"},
            {"category": "mobile-tablets", "attribute": "os", "group": "فنی"},
            {"category": "mobile-tablets", "attribute": "mobile-warranty", "group": "خدمات پس از فروش"},
            {"category": "mobile-accessories", "attribute": "mobile-brand", "group": "عمومی"},
            {"category": "mobile-accessories", "attribute": "mobile-warranty", "group": "خدمات پس از فروش"},
        ],
        "recommended_options": [
            {"category": "mobile-phones", "attribute": "mobile-color"},
            {"category": "mobile-phones", "attribute": "storage"},
            {"category": "mobile-phones", "attribute": "ram"},
            {"category": "mobile-tablets", "attribute": "mobile-color"},
            {"category": "mobile-tablets", "attribute": "storage"},
        ],
    },
    {
        "slug": "computers-laptops", "name": "لپ‌تاپ و کامپیوتر", "icon": "💻", "sector": "digital", "version": 1, "display_order": 12,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های رایانه و لپ‌تاپ.",
        "categories": [
            {"code": "computers-laptops", "name": "لپ‌تاپ", "icon": "💻"},
            {"code": "computers-desktops", "name": "رایانه رومیزی", "icon": "🖥️"},
            {"code": "computers-parts", "name": "قطعات کامپیوتر", "icon": "🔧"},
            {"code": "computers-accessories", "name": "لوازم جانبی رایانه", "icon": "🖱️"},
        ],
        "attributes": [
            {"code": "computer-brand", "label": "برند", "data_type": "text"},
            {"code": "cpu", "label": "پردازنده", "data_type": "text"},
            {"code": "computer-ram", "label": "رم", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["8GB", "16GB", "32GB", "64GB"]},
            {"code": "storage-type", "label": "حافظه ذخیره‌سازی", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["SSD 256GB", "SSD 512GB", "SSD 1TB", "HDD 1TB", "HDD 2TB"]},
            {"code": "gpu", "label": "کارت گرافیک", "data_type": "text"},
            {"code": "computer-screen-size", "label": "اندازه صفحه‌نمایش", "data_type": "number", "unit": "اینچ"},
            {"code": "computer-os", "label": "سیستم‌عامل", "data_type": "select", "display_type": "dropdown",
             "values": ["ویندوز", "لینوکس", "macOS", "بدون سیستم‌عامل"]},
            {"code": "computer-warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "computer-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True, "values": [("مشکی", "#111827"), ("نقره‌ای", "#9ca3af"), ("خاکستری", "#4b5563")]},
        ],
        "mappings": [
            {"category": "computers-laptops", "attribute": "computer-brand", "group": "عمومی", "required": True},
            {"category": "computers-laptops", "attribute": "cpu", "group": "فنی", "required": True},
            {"category": "computers-laptops", "attribute": "gpu", "group": "فنی"},
            {"category": "computers-laptops", "attribute": "computer-screen-size", "group": "فنی"},
            {"category": "computers-laptops", "attribute": "computer-os", "group": "فنی"},
            {"category": "computers-laptops", "attribute": "computer-warranty", "group": "خدمات پس از فروش"},
            {"category": "computers-desktops", "attribute": "computer-brand", "group": "عمومی"},
            {"category": "computers-desktops", "attribute": "cpu", "group": "فنی", "required": True},
            {"category": "computers-desktops", "attribute": "gpu", "group": "فنی"},
            {"category": "computers-desktops", "attribute": "computer-os", "group": "فنی"},
            {"category": "computers-parts", "attribute": "computer-brand", "group": "عمومی"},
            {"category": "computers-accessories", "attribute": "computer-brand", "group": "عمومی"},
        ],
        "recommended_options": [
            {"category": "computers-laptops", "attribute": "computer-color"},
            {"category": "computers-laptops", "attribute": "computer-ram"},
            {"category": "computers-laptops", "attribute": "storage-type"},
            {"category": "computers-desktops", "attribute": "computer-ram"},
            {"category": "computers-desktops", "attribute": "storage-type"},
        ],
    },
    {
        "slug": "home-appliances", "name": "لوازم خانگی برقی", "icon": "🧺", "sector": "home", "version": 1, "display_order": 33,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های لوازم خانگی.",
        "categories": [
            {"code": "appliances-kitchen", "name": "لوازم آشپزخانه", "icon": "🍳"},
            {"code": "appliances-laundry", "name": "لوازم شوینده", "icon": "🧺"},
            {"code": "appliances-climate", "name": "سرمایشی و گرمایشی", "icon": "❄️"},
            {"code": "appliances-personal", "name": "لوازم شخصی", "icon": "💇"},
        ],
        "attributes": [
            {"code": "appliance-brand", "label": "برند", "data_type": "text"},
            {"code": "energy-rating", "label": "رده مصرف انرژی", "data_type": "select", "display_type": "dropdown",
             "values": ["A+++", "A++", "A+", "A", "B", "C"]},
            {"code": "power-consumption", "label": "توان مصرفی", "data_type": "number", "unit": "وات"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
            {"code": "appliance-warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "appliance-origin", "label": "کشور سازنده", "data_type": "text"},
            {"code": "appliance-color", "label": "رنگ بدنه", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("سفید", "#f9fafb"), ("نقره‌ای", "#9ca3af"), ("مشکی", "#111827"), ("قرمز", "#ef4444")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": group, "required": required}
            for cat in ("appliances-kitchen", "appliances-laundry", "appliances-climate", "appliances-personal")
            for attr, group, required in [
                ("appliance-brand", "عمومی", True),
                ("energy-rating", "مشخصات فنی", False),
                ("power-consumption", "مشخصات فنی", False),
                ("dimensions", "مشخصات فنی", False),
                ("appliance-warranty", "خدمات پس از فروش", False),
                ("appliance-origin", "خدمات پس از فروش", False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": "appliance-color"}
            for cat in ("appliances-kitchen", "appliances-laundry", "appliances-climate", "appliances-personal")
        ],
    },
    {
        "slug": "jewelry-accessories", "name": "طلا و جواهرات", "icon": "💍", "sector": "retail", "version": 1, "display_order": 10,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های جواهرات و اکسسوری.",
        "categories": [
            {"code": "jewelry-rings", "name": "انگشتر", "icon": "💍"},
            {"code": "jewelry-necklaces", "name": "گردنبند", "icon": "📿"},
            {"code": "jewelry-bracelets", "name": "دستبند", "icon": "⛓️"},
            {"code": "jewelry-earrings", "name": "گوشواره", "icon": "💎"},
            {"code": "jewelry-watches", "name": "ساعت", "icon": "⌚"},
        ],
        "attributes": [
            {"code": "jewelry-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["طلا", "نقره", "استیل ضدزنگ", "برنز", "پلاتین"]},
            {"code": "gold-purity", "label": "عیار", "data_type": "select", "display_type": "dropdown",
             "values": ["۱۸ عیار", "۲۱ عیار", "۲۲ عیار", "۲۴ عیار"]},
            {"code": "stone-type", "label": "نوع نگین", "data_type": "text"},
            {"code": "jewelry-weight", "label": "وزن", "data_type": "number", "unit": "گرم"},
            {"code": "jewelry-style", "label": "سبک", "data_type": "select", "display_type": "dropdown",
             "values": ["کلاسیک", "مدرن", "مینیمال", "سنتی"]},
            {"code": "jewelry-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["6", "7", "8", "9", "10", "11"]},
            {"code": "jewelry-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True, "values": [("طلایی", "#d4af37"), ("نقره‌ای", "#c0c0c0"), ("رزگلد", "#b76e79")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required}
            for cat in ("jewelry-rings", "jewelry-necklaces", "jewelry-bracelets", "jewelry-earrings")
            for attr, required in [
                ("jewelry-material", True), ("gold-purity", False), ("stone-type", False),
                ("jewelry-weight", False), ("jewelry-style", False),
            ]
        ] + [
            {"category": "jewelry-watches", "attribute": "jewelry-material", "group": "مشخصات", "required": True},
            {"category": "jewelry-watches", "attribute": "jewelry-style", "group": "مشخصات"},
        ],
        "recommended_options": [
            {"category": "jewelry-rings", "attribute": "jewelry-size"},
            {"category": "jewelry-rings", "attribute": "jewelry-color"},
            {"category": "jewelry-necklaces", "attribute": "jewelry-color"},
            {"category": "jewelry-bracelets", "attribute": "jewelry-color"},
            {"category": "jewelry-earrings", "attribute": "jewelry-color"},
        ],
    },
    {
        "slug": "books-stationery", "name": "کتاب و مجله", "icon": "📚", "sector": "culture", "version": 1, "display_order": 61,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های کتاب و لوازم‌التحریر.",
        "categories": [
            {"code": "books", "name": "کتاب", "icon": "📖"},
            {"code": "stationery", "name": "لوازم‌التحریر", "icon": "✏️"},
            {"code": "notebooks-paper", "name": "دفتر و کاغذ", "icon": "📓"},
            {"code": "art-supplies", "name": "لوازم هنری", "icon": "🎨"},
        ],
        "attributes": [
            {"code": "author", "label": "نویسنده", "data_type": "text"},
            {"code": "publisher", "label": "ناشر", "data_type": "text"},
            {"code": "language", "label": "زبان", "data_type": "select", "display_type": "dropdown",
             "values": ["فارسی", "انگلیسی", "سایر"]},
            {"code": "cover-type", "label": "نوع جلد", "data_type": "select", "display_type": "dropdown",
             "values": ["شومیز", "گالینگور", "جلد سخت"]},
            {"code": "page-count", "label": "تعداد صفحات", "data_type": "number"},
            {"code": "subject", "label": "موضوع", "data_type": "select", "display_type": "dropdown",
             "values": ["رمان", "علمی", "کودک و نوجوان", "دانشگاهی", "تاریخی", "روانشناسی"]},
            {"code": "stationery-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("مشکی", "#111827"), ("آبی", "#3b82f6"), ("قرمز", "#ef4444"), ("سبز", "#22c55e")]},
        ],
        "mappings": [
            {"category": "books", "attribute": "author", "group": "مشخصات کتاب", "required": True},
            {"category": "books", "attribute": "publisher", "group": "مشخصات کتاب"},
            {"category": "books", "attribute": "language", "group": "مشخصات کتاب"},
            {"category": "books", "attribute": "cover-type", "group": "مشخصات کتاب"},
            {"category": "books", "attribute": "page-count", "group": "مشخصات کتاب"},
            {"category": "books", "attribute": "subject", "group": "مشخصات کتاب"},
            {"category": "stationery", "attribute": "stationery-color", "group": "مشخصات"},
            {"category": "notebooks-paper", "attribute": "stationery-color", "group": "مشخصات"},
        ],
        "recommended_options": [
            {"category": "stationery", "attribute": "stationery-color"},
            {"category": "notebooks-paper", "attribute": "stationery-color"},
            {"category": "art-supplies", "attribute": "stationery-color"},
        ],
    },
    {
        "slug": "food-grocery", "name": "مواد غذایی و خواروبار", "icon": "🛒", "version": 1, "display_order": 9,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های مواد غذایی و خواروبار.",
        "categories": [
            {"code": "food-dry-goods", "name": "خشکبار", "icon": "🌰"},
            {"code": "food-dairy", "name": "لبنیات", "icon": "🥛"},
            {"code": "food-beverages", "name": "نوشیدنی", "icon": "🥤"},
            {"code": "food-snacks", "name": "میان‌وعده", "icon": "🍪"},
            {"code": "food-spices", "name": "ادویه‌جات", "icon": "🌶️"},
        ],
        "attributes": [
            {"code": "food-brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن خالص", "data_type": "number", "unit": "گرم"},
            {"code": "shelf-life", "label": "مدت ماندگاری", "data_type": "text"},
            {"code": "dietary-info", "label": "رژیم غذایی", "data_type": "multiselect", "display_type": "checkbox",
             "values": ["گیاهی", "بدون گلوتن", "ارگانیک", "کم‌چرب", "بدون‌شکر"]},
            {"code": "food-origin", "label": "کشور تولید", "data_type": "text"},
            {"code": "package-size", "label": "حجم/وزن بسته‌بندی", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["250گرم", "500گرم", "1کیلوگرم", "2.5کیلوگرم", "5کیلوگرم"]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required}
            for cat in ("food-dry-goods", "food-dairy", "food-beverages", "food-snacks", "food-spices")
            for attr, required in [
                ("food-brand", True), ("net-weight", False), ("shelf-life", False),
                ("dietary-info", False), ("food-origin", False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": "package-size"}
            for cat in ("food-dry-goods", "food-dairy", "food-beverages", "food-snacks", "food-spices")
        ],
    },
    {
        "slug": "furniture-decor", "name": "مبلمان و دکوراسیون", "icon": "🛋️", "sector": "home", "version": 1, "display_order": 34,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های مبلمان و دکوراسیون منزل.",
        "categories": [
            {"code": "furniture-seating", "name": "مبل و صندلی", "icon": "🛋️"},
            {"code": "furniture-tables", "name": "میز", "icon": "🪑"},
            {"code": "furniture-beds", "name": "تخت‌خواب", "icon": "🛏️"},
            {"code": "furniture-decor", "name": "دکوراسیون", "icon": "🖼️"},
            {"code": "furniture-lighting", "name": "نورپردازی", "icon": "💡"},
        ],
        "attributes": [
            {"code": "furniture-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["چوب طبیعی", "فلز", "MDF", "پارچه‌ای", "چرم", "شیشه"]},
            {"code": "furniture-style", "label": "سبک", "data_type": "select", "display_type": "dropdown",
             "values": ["کلاسیک", "مدرن", "مینیمال", "صنعتی", "روستیک"]},
            {"code": "furniture-dimensions", "label": "ابعاد", "data_type": "text"},
            {"code": "weight-capacity", "label": "وزن قابل تحمل", "data_type": "number", "unit": "کیلوگرم"},
            {"code": "foldable", "label": "قابل تاشدن", "data_type": "boolean"},
            {"code": "furniture-color", "label": "رنگ", "data_type": "color", "display_type": "swatch",
             "is_variant_axis": True,
             "values": [("قهوه‌ای", "#78350f"), ("مشکی", "#111827"), ("سفید", "#f9fafb"), ("بژ", "#e5d3b3")]},
        ],
        "mappings": [
            {"category": cat, "attribute": attr, "group": "مشخصات", "required": required}
            for cat in ("furniture-seating", "furniture-tables", "furniture-beds", "furniture-decor", "furniture-lighting")
            for attr, required in [
                ("furniture-material", True), ("furniture-style", False),
                ("furniture-dimensions", False), ("weight-capacity", False), ("foldable", False),
            ]
        ],
        "recommended_options": [
            {"category": cat, "attribute": "furniture-color"}
            for cat in ("furniture-seating", "furniture-tables", "furniture-beds", "furniture-decor", "furniture-lighting")
        ],
    },
]
