"""بخشِ صنف‌هایِ کاتالوگِ تأییدشده (۱۰۰ صنف + «سایر») که در فایل‌هایِ قدیمیِ
صنف بازاستفاده نشده‌اند — نگاه کنید به ``apps.catalog.industry_templates.registry``
برایِ نگاشتِ کاملِ ۱۰۰+۱ صنفِ تأییدشده به رکوردهای موجود/جدید.

شاملِ ۲ صنفِ غنی که کاملاً دستی نوشته شده‌اند («پوشاک مردانه» و «تجهیزات
سرمایشِ و گرمایش» — طبقِ نمونه‌هایِ داده‌شده در دستورِ کار)، ۱ صنفِ «سایر»
(فقط یک دسته‌بندیِ جای‌گیرنده، بدونِ ویژگی — بخشِ ۱۳)، و ۷۴ صنفِ «کمینه‌یِ
مفید» — هرکدام یک دسته‌بندیِ تک‌سطحی (بدونِ زیرشاخه، خودش قابلِ انتخاب برایِ
کالا) به‌همراه چند ویژگیِ توصیفیِ متنی (فقط ``text`` — بخشِ ۱۱، بدونِ
رنگ/سواچ). صنف‌هایِ خدماتی (رستهِ ``services``) هیچ ویژگی‌ای ندارند."""

APPROVED_CATALOG_TEMPLATES = [
    {
        "slug": "mens-clothing", "name": "پوشاک مردانه", "icon": "👔", "sector": "retail",
        "version": 1, "display_order": 1,
        "description": "دسته‌بندی، ویژگی‌های توصیفی و محورهای تنوع استاندارد برای فروشگاه‌های پوشاک مردانه.",
        "categories": [
            {"code": "mens-clothing", "name": "پوشاک مردانه", "icon": "👔", "children": [
                {"code": "mens-clothing-tops", "name": "پوشاک بالاتنه", "icon": "👕", "children": [
                    {"code": "mens-clothing-tshirts", "name": "تی‌شرت", "icon": "👕"},
                    {"code": "mens-clothing-shirts", "name": "پیراهن", "icon": "👔"},
                    {"code": "mens-clothing-sweatshirts", "name": "سویشرت", "icon": "👕"},
                ]},
                {"code": "mens-clothing-bottoms", "name": "پوشاک پایین‌تنه", "icon": "👖", "children": [
                    {"code": "mens-clothing-pants", "name": "شلوار", "icon": "👖"},
                    {"code": "mens-clothing-shorts", "name": "شلوارک", "icon": "🩳"},
                ]},
                {"code": "mens-clothing-formal", "name": "لباس رسمی", "icon": "🤵"},
                {"code": "mens-clothing-casual", "name": "لباس راحتی", "icon": "🧥"},
                {"code": "mens-clothing-accessories", "name": "اکسسوری مردانه", "icon": "🧣"},
            ]},
        ],
        "attributes": [
            {"code": "mens-color", "label": "رنگ", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True,
             "values": ["مشکی", "سفید", "طوسی", "سرمه‌ای", "قهوه‌ای", "سبز", "آبی", "قرمز"]},
            {"code": "mens-size", "label": "سایز", "data_type": "select", "display_type": "dropdown",
             "is_variant_axis": True, "values": ["S", "M", "L", "XL", "XXL"]},
            {"code": "mens-material", "label": "جنس", "data_type": "select", "display_type": "dropdown",
             "values": ["نخی", "پلی‌استر", "کتان", "دنیم", "پشمی", "چرم"]},
            {"code": "mens-model", "label": "مدل", "data_type": "text"},
            {"code": "mens-origin-country", "label": "کشور سازنده", "data_type": "text"},
            {"code": "mens-season", "label": "فصل", "data_type": "select", "display_type": "dropdown",
             "values": ["بهار", "تابستان", "پاییز", "زمستان", "همه‌فصل"]},
            {"code": "mens-sleeve-type", "label": "نوع آستین", "data_type": "select", "display_type": "dropdown",
             "values": ["آستین‌کوتاه", "آستین‌بلند", "بدون‌آستین"]},
        ],
        "mappings": [
            {"category": "mens-clothing-tops", "attribute": "mens-material", "group": "عمومی", "required": True, "filterable": True},
            {"category": "mens-clothing-tops", "attribute": "mens-model", "group": "عمومی"},
            {"category": "mens-clothing-tops", "attribute": "mens-season", "group": "عمومی", "filterable": True},
            {"category": "mens-clothing-tops", "attribute": "mens-sleeve-type", "group": "عمومی"},
            {"category": "mens-clothing-tops", "attribute": "mens-origin-country", "group": "سایر"},
            {"category": "mens-clothing-bottoms", "attribute": "mens-material", "group": "عمومی", "required": True, "filterable": True},
            {"category": "mens-clothing-bottoms", "attribute": "mens-model", "group": "عمومی"},
            {"category": "mens-clothing-bottoms", "attribute": "mens-season", "group": "عمومی"},
            {"category": "mens-clothing-bottoms", "attribute": "mens-origin-country", "group": "سایر"},
            {"category": "mens-clothing-formal", "attribute": "mens-material", "group": "عمومی", "required": True},
            {"category": "mens-clothing-formal", "attribute": "mens-model", "group": "عمومی"},
            {"category": "mens-clothing-casual", "attribute": "mens-material", "group": "عمومی"},
            {"category": "mens-clothing-casual", "attribute": "mens-season", "group": "عمومی"},
            {"category": "mens-clothing-accessories", "attribute": "mens-material", "group": "عمومی"},
        ],
        "recommended_options": [
            {"category": "mens-clothing-tops", "attribute": "mens-color"},
            {"category": "mens-clothing-tops", "attribute": "mens-size"},
            {"category": "mens-clothing-bottoms", "attribute": "mens-color"},
            {"category": "mens-clothing-bottoms", "attribute": "mens-size"},
            {"category": "mens-clothing-formal", "attribute": "mens-color"},
            {"category": "mens-clothing-formal", "attribute": "mens-size"},
            {"category": "mens-clothing-casual", "attribute": "mens-color"},
            {"category": "mens-clothing-casual", "attribute": "mens-size"},
        ],
    },
    {
        "slug": "hvac-equipment", "name": "تجهیزات سرمایش و گرمایش", "icon": "❄", "sector": "industry",
        "version": 1, "display_order": 89,
        "description": "دسته‌بندی و ویژگی‌های استاندارد برای فروشگاه‌های تجهیزات سرمایش و گرمایش.",
        "categories": [
            {"code": "hvac-cooling", "name": "تجهیزات سرمایش", "icon": "❄"},
            {"code": "hvac-heating", "name": "تجهیزات گرمایش", "icon": "🔥"},
            {"code": "hvac-ventilation", "name": "تهویه و کنترل هوا", "icon": "🌬"},
            {"code": "hvac-parts", "name": "قطعات و لوازم جانبی", "icon": "🧩"},
        ],
        "attributes": [
            {"code": "hvac-brand", "label": "برند", "data_type": "text"},
            {"code": "hvac-model", "label": "مدل", "data_type": "text"},
            {"code": "hvac-capacity", "label": "ظرفیت", "data_type": "text"},
            {"code": "hvac-power", "label": "توان", "data_type": "text"},
            {"code": "hvac-energy-type", "label": "نوع انرژی", "data_type": "select", "display_type": "dropdown",
             "values": ["برق", "گاز", "گازوئیل", "هیبریدی"]},
            {"code": "hvac-dimensions", "label": "ابعاد", "data_type": "text"},
            {"code": "hvac-weight", "label": "وزن", "data_type": "text"},
            {"code": "hvac-warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "hvac-origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "hvac-cooling", "attribute": "hvac-brand", "group": "مشخصات فنی", "required": True, "filterable": True},
            {"category": "hvac-cooling", "attribute": "hvac-model", "group": "مشخصات فنی"},
            {"category": "hvac-cooling", "attribute": "hvac-capacity", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-cooling", "attribute": "hvac-power", "group": "مشخصات فنی"},
            {"category": "hvac-cooling", "attribute": "hvac-energy-type", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-cooling", "attribute": "hvac-dimensions", "group": "ابعاد و وزن"},
            {"category": "hvac-cooling", "attribute": "hvac-weight", "group": "ابعاد و وزن"},
            {"category": "hvac-cooling", "attribute": "hvac-warranty", "group": "سایر"},
            {"category": "hvac-cooling", "attribute": "hvac-origin-country", "group": "سایر"},
            {"category": "hvac-heating", "attribute": "hvac-brand", "group": "مشخصات فنی", "required": True, "filterable": True},
            {"category": "hvac-heating", "attribute": "hvac-model", "group": "مشخصات فنی"},
            {"category": "hvac-heating", "attribute": "hvac-capacity", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-heating", "attribute": "hvac-power", "group": "مشخصات فنی"},
            {"category": "hvac-heating", "attribute": "hvac-energy-type", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-heating", "attribute": "hvac-warranty", "group": "سایر"},
            {"category": "hvac-heating", "attribute": "hvac-origin-country", "group": "سایر"},
            {"category": "hvac-ventilation", "attribute": "hvac-brand", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-ventilation", "attribute": "hvac-power", "group": "مشخصات فنی"},
            {"category": "hvac-ventilation", "attribute": "hvac-dimensions", "group": "ابعاد و وزن"},
            {"category": "hvac-parts", "attribute": "hvac-brand", "group": "مشخصات فنی", "filterable": True},
            {"category": "hvac-parts", "attribute": "hvac-model", "group": "مشخصات فنی"},
        ],
    },
    {
        "slug": "other", "name": "سایر (صنف آزاد)", "icon": "✨", "sector": "other",
        "version": 1, "display_order": 101,
        "description": "برای کسب‌وکارهایی که در فهرست صنوف نمی‌گنجند — دسته‌بندی و ویژگی به‌صورت دستی ساخته می‌شود.",
        "categories": [
            {"code": "other", "name": "سایر", "icon": "✨"},
        ],
        "attributes": [],
    },
    {
        "slug": "womens-clothing", "name": "پوشاک زنانه", "icon": "👗", "sector": "retail",
        "version": 1, "display_order": 2,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های پوشاک زنانه.",
        "categories": [
            {"code": "womens-clothing", "name": "پوشاک زنانه", "icon": "👗"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "womens-clothing", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "womens-clothing", "attribute": "material", "group": "مشخصات"},
            {"category": "womens-clothing", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "kids-baby-clothing", "name": "پوشاک کودک و نوزاد", "icon": "🧸", "sector": "retail",
        "version": 1, "display_order": 3,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های پوشاک کودک و نوزاد.",
        "categories": [
            {"code": "kids-baby-clothing", "name": "پوشاک کودک و نوزاد", "icon": "🧸"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "kids-baby-clothing", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "kids-baby-clothing", "attribute": "material", "group": "مشخصات"},
            {"category": "kids-baby-clothing", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "scarves-shawls", "name": "شال و روسری", "icon": "🧣", "sector": "retail",
        "version": 1, "display_order": 8,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های شال و روسری.",
        "categories": [
            {"code": "scarves-shawls", "name": "شال و روسری", "icon": "🧣"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "scarves-shawls", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "scarves-shawls", "attribute": "material", "group": "مشخصات"},
            {"category": "scarves-shawls", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "multi-category-store", "name": "فروشگاه چند منظوره", "icon": "🛍", "sector": "retail",
        "version": 1, "display_order": 9,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های فروشگاه چند منظوره.",
        "categories": [
            {"code": "multi-category-store", "name": "فروشگاه چند منظوره", "icon": "🛍"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "multi-category-store", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "multi-category-store", "attribute": "material", "group": "مشخصات"},
            {"category": "multi-category-store", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "audio-video", "name": "صوتی و تصویری", "icon": "🎧", "sector": "digital",
        "version": 1, "display_order": 13,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های صوتی و تصویری.",
        "categories": [
            {"code": "audio-video", "name": "صوتی و تصویری", "icon": "🎧"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "audio-video", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "audio-video", "attribute": "model", "group": "مشخصات"},
            {"category": "audio-video", "attribute": "warranty", "group": "مشخصات"},
            {"category": "audio-video", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "cameras-photography", "name": "دوربین عکاسی", "icon": "📷", "sector": "digital",
        "version": 1, "display_order": 14,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های دوربین عکاسی.",
        "categories": [
            {"code": "cameras-photography", "name": "دوربین عکاسی", "icon": "📷"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "cameras-photography", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "cameras-photography", "attribute": "model", "group": "مشخصات"},
            {"category": "cameras-photography", "attribute": "warranty", "group": "مشخصات"},
            {"category": "cameras-photography", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "gaming-consoles", "name": "کنسول بازی و گیمینگ", "icon": "🎮", "sector": "digital",
        "version": 1, "display_order": 15,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های کنسول بازی و گیمینگ.",
        "categories": [
            {"code": "gaming-consoles", "name": "کنسول بازی و گیمینگ", "icon": "🎮"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "gaming-consoles", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "gaming-consoles", "attribute": "model", "group": "مشخصات"},
            {"category": "gaming-consoles", "attribute": "warranty", "group": "مشخصات"},
            {"category": "gaming-consoles", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "computer-accessories", "name": "لوازم جانبی کامپیوتر", "icon": "⌨", "sector": "digital",
        "version": 1, "display_order": 16,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم جانبی کامپیوتر.",
        "categories": [
            {"code": "computer-accessories", "name": "لوازم جانبی کامپیوتر", "icon": "⌨"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "computer-accessories", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "computer-accessories", "attribute": "model", "group": "مشخصات"},
            {"category": "computer-accessories", "attribute": "warranty", "group": "مشخصات"},
            {"category": "computer-accessories", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "computer-parts-hardware", "name": "قطعات و سخت‌افزار", "icon": "🖥", "sector": "digital",
        "version": 1, "display_order": 17,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های قطعات و سخت‌افزار.",
        "categories": [
            {"code": "computer-parts-hardware", "name": "قطعات و سخت‌افزار", "icon": "🖥"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "computer-parts-hardware", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "computer-parts-hardware", "attribute": "model", "group": "مشخصات"},
            {"category": "computer-parts-hardware", "attribute": "warranty", "group": "مشخصات"},
            {"category": "computer-parts-hardware", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "smart-gadgets", "name": "گجت‌های هوشمند", "icon": "💡", "sector": "digital",
        "version": 1, "display_order": 18,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های گجت‌های هوشمند.",
        "categories": [
            {"code": "smart-gadgets", "name": "گجت‌های هوشمند", "icon": "💡"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "smart-gadgets", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "smart-gadgets", "attribute": "model", "group": "مشخصات"},
            {"category": "smart-gadgets", "attribute": "warranty", "group": "مشخصات"},
            {"category": "smart-gadgets", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "network-internet-equipment", "name": "تجهیزات شبکه و اینترنت", "icon": "📡", "sector": "digital",
        "version": 1, "display_order": 20,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های تجهیزات شبکه و اینترنت.",
        "categories": [
            {"code": "network-internet-equipment", "name": "تجهیزات شبکه و اینترنت", "icon": "📡"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "model", "label": "مدل", "data_type": "text"},
            {"code": "warranty", "label": "گارانتی", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "network-internet-equipment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "network-internet-equipment", "attribute": "model", "group": "مشخصات"},
            {"category": "network-internet-equipment", "attribute": "warranty", "group": "مشخصات"},
            {"category": "network-internet-equipment", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "nuts-dried-fruits", "name": "خشکبار و آجیل", "icon": "🥜", "sector": "food",
        "version": 1, "display_order": 21,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های خشکبار و آجیل.",
        "categories": [
            {"code": "nuts-dried-fruits", "name": "خشکبار و آجیل", "icon": "🥜"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "nuts-dried-fruits", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "nuts-dried-fruits", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "nuts-dried-fruits", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "sweets-chocolate", "name": "شیرینی و شکلات", "icon": "🍫", "sector": "food",
        "version": 1, "display_order": 22,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های شیرینی و شکلات.",
        "categories": [
            {"code": "sweets-chocolate", "name": "شیرینی و شکلات", "icon": "🍫"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "sweets-chocolate", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "sweets-chocolate", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "sweets-chocolate", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "tea-coffee", "name": "چای و قهوه", "icon": "☕", "sector": "food",
        "version": 1, "display_order": 23,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های چای و قهوه.",
        "categories": [
            {"code": "tea-coffee", "name": "چای و قهوه", "icon": "☕"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "tea-coffee", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "tea-coffee", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "tea-coffee", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "honey-natural-products", "name": "عسل و محصولات طبیعی", "icon": "🍯", "sector": "food",
        "version": 1, "display_order": 24,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های عسل و محصولات طبیعی.",
        "categories": [
            {"code": "honey-natural-products", "name": "عسل و محصولات طبیعی", "icon": "🍯"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "honey-natural-products", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "honey-natural-products", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "honey-natural-products", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "spices-saffron", "name": "ادویه و زعفران", "icon": "🧂", "sector": "food",
        "version": 1, "display_order": 25,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ادویه و زعفران.",
        "categories": [
            {"code": "spices-saffron", "name": "ادویه و زعفران", "icon": "🧂"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "spices-saffron", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "spices-saffron", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "spices-saffron", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "meat-poultry", "name": "گوشت و مرغ", "icon": "🥩", "sector": "food",
        "version": 1, "display_order": 26,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های گوشت و مرغ.",
        "categories": [
            {"code": "meat-poultry", "name": "گوشت و مرغ", "icon": "🥩"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "meat-poultry", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "meat-poultry", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "meat-poultry", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "fruits-vegetables", "name": "میوه و سبزی", "icon": "🍎", "sector": "food",
        "version": 1, "display_order": 27,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های میوه و سبزی.",
        "categories": [
            {"code": "fruits-vegetables", "name": "میوه و سبزی", "icon": "🍎"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "fruits-vegetables", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "fruits-vegetables", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "fruits-vegetables", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "dairy-cheese", "name": "لبنیات و پنیر", "icon": "🧀", "sector": "food",
        "version": 1, "display_order": 28,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لبنیات و پنیر.",
        "categories": [
            {"code": "dairy-cheese", "name": "لبنیات و پنیر", "icon": "🧀"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "dairy-cheese", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "dairy-cheese", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "dairy-cheese", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "beverages-juice", "name": "نوشیدنی و آبمیوه", "icon": "🥤", "sector": "food",
        "version": 1, "display_order": 29,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های نوشیدنی و آبمیوه.",
        "categories": [
            {"code": "beverages-juice", "name": "نوشیدنی و آبمیوه", "icon": "🥤"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "beverages-juice", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "beverages-juice", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "beverages-juice", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "bread-pastry", "name": "نان و قنادی", "icon": "🍞", "sector": "food",
        "version": 1, "display_order": 30,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های نان و قنادی.",
        "categories": [
            {"code": "bread-pastry", "name": "نان و قنادی", "icon": "🍞"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "net-weight", "label": "وزن یا حجم خالص", "data_type": "text"},
            {"code": "origin-country", "label": "کشور مبدأ", "data_type": "text"},
        ],
        "mappings": [
            {"category": "bread-pastry", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "bread-pastry", "attribute": "net-weight", "group": "مشخصات"},
            {"category": "bread-pastry", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "tableware-dinnerware", "name": "ظروف و سرویس غذا", "icon": "🍽", "sector": "home",
        "version": 1, "display_order": 32,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ظروف و سرویس غذا.",
        "categories": [
            {"code": "tableware-dinnerware", "name": "ظروف و سرویس غذا", "icon": "🍽"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "tableware-dinnerware", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "tableware-dinnerware", "attribute": "material", "group": "مشخصات"},
            {"category": "tableware-dinnerware", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "wooden-furniture-tables", "name": "لوازم چوبی و میز", "icon": "🪑", "sector": "home",
        "version": 1, "display_order": 35,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم چوبی و میز.",
        "categories": [
            {"code": "wooden-furniture-tables", "name": "لوازم چوبی و میز", "icon": "🪑"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "wooden-furniture-tables", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "wooden-furniture-tables", "attribute": "material", "group": "مشخصات"},
            {"category": "wooden-furniture-tables", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "carpets-rugs", "name": "فرش و گلیم", "icon": "🧵", "sector": "home",
        "version": 1, "display_order": 36,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های فرش و گلیم.",
        "categories": [
            {"code": "carpets-rugs", "name": "فرش و گلیم", "icon": "🧵"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "carpets-rugs", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "carpets-rugs", "attribute": "material", "group": "مشخصات"},
            {"category": "carpets-rugs", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "lighting-lamps", "name": "نورپردازی و چراغ", "icon": "💡", "sector": "home",
        "version": 1, "display_order": 37,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های نورپردازی و چراغ.",
        "categories": [
            {"code": "lighting-lamps", "name": "نورپردازی و چراغ", "icon": "💡"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "lighting-lamps", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "lighting-lamps", "attribute": "material", "group": "مشخصات"},
            {"category": "lighting-lamps", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "gardening-plants", "name": "باغبانی و گیاه", "icon": "🪴", "sector": "home",
        "version": 1, "display_order": 39,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های باغبانی و گیاه.",
        "categories": [
            {"code": "gardening-plants", "name": "باغبانی و گیاه", "icon": "🪴"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "gardening-plants", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "gardening-plants", "attribute": "material", "group": "مشخصات"},
            {"category": "gardening-plants", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "cleaning-tools", "name": "ابزار تمیزکاری", "icon": "🧹", "sector": "home",
        "version": 1, "display_order": 40,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ابزار تمیزکاری.",
        "categories": [
            {"code": "cleaning-tools", "name": "ابزار تمیزکاری", "icon": "🧹"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "cleaning-tools", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "cleaning-tools", "attribute": "material", "group": "مشخصات"},
            {"category": "cleaning-tools", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "online-pharmacy", "name": "داروخانه آنلاین", "icon": "💊", "sector": "beauty",
        "version": 1, "display_order": 44,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های داروخانه آنلاین.",
        "categories": [
            {"code": "online-pharmacy", "name": "داروخانه آنلاین", "icon": "💊"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "online-pharmacy", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "online-pharmacy", "attribute": "volume", "group": "مشخصات"},
            {"category": "online-pharmacy", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "medical-equipment", "name": "تجهیزات پزشکی", "icon": "🩺", "sector": "beauty",
        "version": 1, "display_order": 45,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های تجهیزات پزشکی.",
        "categories": [
            {"code": "medical-equipment", "name": "تجهیزات پزشکی", "icon": "🩺"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "medical-equipment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "medical-equipment", "attribute": "volume", "group": "مشخصات"},
            {"category": "medical-equipment", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "supplements-organic", "name": "مکمل و محصولات ارگانیک", "icon": "🌿", "sector": "beauty",
        "version": 1, "display_order": 46,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های مکمل و محصولات ارگانیک.",
        "categories": [
            {"code": "supplements-organic", "name": "مکمل و محصولات ارگانیک", "icon": "🌿"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "supplements-organic", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "supplements-organic", "attribute": "volume", "group": "مشخصات"},
            {"category": "supplements-organic", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "health-massage-devices", "name": "لوازم سلامت و ماساژ", "icon": "💆", "sector": "beauty",
        "version": 1, "display_order": 47,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم سلامت و ماساژ.",
        "categories": [
            {"code": "health-massage-devices", "name": "لوازم سلامت و ماساژ", "icon": "💆"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "health-massage-devices", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "health-massage-devices", "attribute": "volume", "group": "مشخصات"},
            {"category": "health-massage-devices", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "oral-dental-care", "name": "مراقبت دهان و دندان", "icon": "🦷", "sector": "beauty",
        "version": 1, "display_order": 48,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های مراقبت دهان و دندان.",
        "categories": [
            {"code": "oral-dental-care", "name": "مراقبت دهان و دندان", "icon": "🦷"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "oral-dental-care", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "oral-dental-care", "attribute": "volume", "group": "مشخصات"},
            {"category": "oral-dental-care", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "sun-protection", "name": "محافظت از آفتاب", "icon": "☀", "sector": "beauty",
        "version": 1, "display_order": 50,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های محافظت از آفتاب.",
        "categories": [
            {"code": "sun-protection", "name": "محافظت از آفتاب", "icon": "☀"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "volume", "label": "حجم", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "sun-protection", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "sun-protection", "attribute": "volume", "group": "مشخصات"},
            {"category": "sun-protection", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "balls-play-equipment", "name": "توپ و لوازم بازی", "icon": "⚽", "sector": "sport",
        "version": 1, "display_order": 51,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های توپ و لوازم بازی.",
        "categories": [
            {"code": "balls-play-equipment", "name": "توپ و لوازم بازی", "icon": "⚽"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "balls-play-equipment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "balls-play-equipment", "attribute": "size-model", "group": "مشخصات"},
            {"category": "balls-play-equipment", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "bicycles-scooters", "name": "دوچرخه و اسکوتر", "icon": "🚴", "sector": "sport",
        "version": 1, "display_order": 53,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های دوچرخه و اسکوتر.",
        "categories": [
            {"code": "bicycles-scooters", "name": "دوچرخه و اسکوتر", "icon": "🚴"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "bicycles-scooters", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "bicycles-scooters", "attribute": "size-model", "group": "مشخصات"},
            {"category": "bicycles-scooters", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "camping-outdoor", "name": "کمپینگ و طبیعت‌گردی", "icon": "🏕", "sector": "sport",
        "version": 1, "display_order": 54,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های کمپینگ و طبیعت‌گردی.",
        "categories": [
            {"code": "camping-outdoor", "name": "کمپینگ و طبیعت‌گردی", "icon": "🏕"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "camping-outdoor", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "camping-outdoor", "attribute": "size-model", "group": "مشخصات"},
            {"category": "camping-outdoor", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "winter-sports", "name": "ورزش زمستانی", "icon": "🎿", "sector": "sport",
        "version": 1, "display_order": 55,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ورزش زمستانی.",
        "categories": [
            {"code": "winter-sports", "name": "ورزش زمستانی", "icon": "🎿"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "winter-sports", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "winter-sports", "attribute": "size-model", "group": "مشخصات"},
            {"category": "winter-sports", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "martial-arts", "name": "ورزش‌های رزمی", "icon": "🥋", "sector": "sport",
        "version": 1, "display_order": 56,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ورزش‌های رزمی.",
        "categories": [
            {"code": "martial-arts", "name": "ورزش‌های رزمی", "icon": "🥋"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "martial-arts", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "martial-arts", "attribute": "size-model", "group": "مشخصات"},
            {"category": "martial-arts", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "hunting-fishing", "name": "شکار و ماهیگیری", "icon": "🎣", "sector": "sport",
        "version": 1, "display_order": 57,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های شکار و ماهیگیری.",
        "categories": [
            {"code": "hunting-fishing", "name": "شکار و ماهیگیری", "icon": "🎣"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "hunting-fishing", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "hunting-fishing", "attribute": "size-model", "group": "مشخصات"},
            {"category": "hunting-fishing", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "sports-event-tickets", "name": "بلیت رویداد ورزشی", "icon": "🎯", "sector": "sport",
        "version": 1, "display_order": 58,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های بلیت رویداد ورزشی.",
        "categories": [
            {"code": "sports-event-tickets", "name": "بلیت رویداد ورزشی", "icon": "🎯"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "sports-event-tickets", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "sports-event-tickets", "attribute": "size-model", "group": "مشخصات"},
            {"category": "sports-event-tickets", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "board-games-entertainment", "name": "بازی فکری و سرگرمی", "icon": "♟", "sector": "sport",
        "version": 1, "display_order": 60,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های بازی فکری و سرگرمی.",
        "categories": [
            {"code": "board-games-entertainment", "name": "بازی فکری و سرگرمی", "icon": "♟"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "size-model", "label": "سایز یا مدل", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "board-games-entertainment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "board-games-entertainment", "attribute": "size-model", "group": "مشخصات"},
            {"category": "board-games-entertainment", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "textbooks-study-aids", "name": "کتاب درسی و کمک‌آموزشی", "icon": "📖", "sector": "culture",
        "version": 1, "display_order": 62,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های کتاب درسی و کمک‌آموزشی.",
        "categories": [
            {"code": "textbooks-study-aids", "name": "کتاب درسی و کمک‌آموزشی", "icon": "📖"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "textbooks-study-aids", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "textbooks-study-aids", "attribute": "usage", "group": "مشخصات"},
            {"category": "textbooks-study-aids", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "stationery-supplies", "name": "لوازم التحریر", "icon": "✏", "sector": "culture",
        "version": 1, "display_order": 63,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم التحریر.",
        "categories": [
            {"code": "stationery-supplies", "name": "لوازم التحریر", "icon": "✏"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "stationery-supplies", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "stationery-supplies", "attribute": "usage", "group": "مشخصات"},
            {"category": "stationery-supplies", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "online-courses", "name": "دوره آموزشی آنلاین", "icon": "🎓", "sector": "culture",
        "version": 1, "display_order": 64,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های دوره آموزشی آنلاین.",
        "categories": [
            {"code": "online-courses", "name": "دوره آموزشی آنلاین", "icon": "🎓"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "online-courses", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "online-courses", "attribute": "usage", "group": "مشخصات"},
            {"category": "online-courses", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "art-painting-supplies", "name": "لوازم هنری و نقاشی", "icon": "🎨", "sector": "culture",
        "version": 1, "display_order": 65,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم هنری و نقاشی.",
        "categories": [
            {"code": "art-painting-supplies", "name": "لوازم هنری و نقاشی", "icon": "🎨"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "art-painting-supplies", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "art-painting-supplies", "attribute": "usage", "group": "مشخصات"},
            {"category": "art-painting-supplies", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "handicrafts", "name": "صنایع دستی", "icon": "🏺", "sector": "culture",
        "version": 1, "display_order": 66,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های صنایع دستی.",
        "categories": [
            {"code": "handicrafts", "name": "صنایع دستی", "icon": "🏺"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "handicrafts", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "handicrafts", "attribute": "usage", "group": "مشخصات"},
            {"category": "handicrafts", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "cultural-media-products", "name": "محصولات فرهنگی و رسانه", "icon": "📰", "sector": "culture",
        "version": 1, "display_order": 68,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های محصولات فرهنگی و رسانه.",
        "categories": [
            {"code": "cultural-media-products", "name": "محصولات فرهنگی و رسانه", "icon": "📰"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "cultural-media-products", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "cultural-media-products", "attribute": "usage", "group": "مشخصات"},
            {"category": "cultural-media-products", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "wall-art-decor", "name": "تابلو و تزئینات هنری", "icon": "🖼", "sector": "culture",
        "version": 1, "display_order": 69,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های تابلو و تزئینات هنری.",
        "categories": [
            {"code": "wall-art-decor", "name": "تابلو و تزئینات هنری", "icon": "🖼"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "wall-art-decor", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "wall-art-decor", "attribute": "usage", "group": "مشخصات"},
            {"category": "wall-art-decor", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "luxury-stationery", "name": "لوازم تحریر لوکس", "icon": "🖋", "sector": "culture",
        "version": 1, "display_order": 70,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم تحریر لوکس.",
        "categories": [
            {"code": "luxury-stationery", "name": "لوازم تحریر لوکس", "icon": "🖋"},
        ],
        "attributes": [
            {"code": "brand-publisher", "label": "برند یا ناشر", "data_type": "text"},
            {"code": "usage", "label": "کاربرد", "data_type": "text"},
            {"code": "material", "label": "جنس", "data_type": "text"},
        ],
        "mappings": [
            {"category": "luxury-stationery", "attribute": "brand-publisher", "group": "مشخصات", "filterable": True},
            {"category": "luxury-stationery", "attribute": "usage", "group": "مشخصات"},
            {"category": "luxury-stationery", "attribute": "material", "group": "مشخصات"},
        ],
    },
    {
        "slug": "tires-wheels", "name": "لاستیک و رینگ", "icon": "🛞", "sector": "auto",
        "version": 1, "display_order": 73,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لاستیک و رینگ.",
        "categories": [
            {"code": "tires-wheels", "name": "لاستیک و رینگ", "icon": "🛞"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "tires-wheels", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "tires-wheels", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "tires-wheels", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "oil-filters", "name": "روغن و فیلتر", "icon": "⛽", "sector": "auto",
        "version": 1, "display_order": 74,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های روغن و فیلتر.",
        "categories": [
            {"code": "oil-filters", "name": "روغن و فیلتر", "icon": "⛽"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "oil-filters", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "oil-filters", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "oil-filters", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "car-accessories-decor", "name": "لوازم تزئینی خودرو", "icon": "🚙", "sector": "auto",
        "version": 1, "display_order": 75,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم تزئینی خودرو.",
        "categories": [
            {"code": "car-accessories-decor", "name": "لوازم تزئینی خودرو", "icon": "🚙"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "car-accessories-decor", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "car-accessories-decor", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "car-accessories-decor", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "car-battery-electrical", "name": "باطری و برق خودرو", "icon": "🔋", "sector": "auto",
        "version": 1, "display_order": 77,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های باطری و برق خودرو.",
        "categories": [
            {"code": "car-battery-electrical", "name": "باطری و برق خودرو", "icon": "🔋"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "car-battery-electrical", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "car-battery-electrical", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "car-battery-electrical", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "heavy-vehicle-parts", "name": "لوازم خودرو سنگین", "icon": "🛻", "sector": "auto",
        "version": 1, "display_order": 78,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های لوازم خودرو سنگین.",
        "categories": [
            {"code": "heavy-vehicle-parts", "name": "لوازم خودرو سنگین", "icon": "🛻"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "heavy-vehicle-parts", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "heavy-vehicle-parts", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "heavy-vehicle-parts", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "farm-garden-tools", "name": "ابزار باغبان و کشاورزی", "icon": "🛠", "sector": "auto",
        "version": 1, "display_order": 79,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ابزار باغبان و کشاورزی.",
        "categories": [
            {"code": "farm-garden-tools", "name": "ابزار باغبان و کشاورزی", "icon": "🛠"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "farm-garden-tools", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "farm-garden-tools", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "farm-garden-tools", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "bicycles-parts", "name": "دوچرخه و لوازم", "icon": "🚲", "sector": "auto",
        "version": 1, "display_order": 80,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های دوچرخه و لوازم.",
        "categories": [
            {"code": "bicycles-parts", "name": "دوچرخه و لوازم", "icon": "🚲"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "compatible-model", "label": "خودروی سازگار", "data_type": "text"},
            {"code": "origin-country", "label": "کشور سازنده", "data_type": "text"},
        ],
        "mappings": [
            {"category": "bicycles-parts", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "bicycles-parts", "attribute": "compatible-model", "group": "مشخصات"},
            {"category": "bicycles-parts", "attribute": "origin-country", "group": "مشخصات"},
        ],
    },
    {
        "slug": "building-materials", "name": "مصالح ساختمانی", "icon": "🧱", "sector": "industry",
        "version": 1, "display_order": 81,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های مصالح ساختمانی.",
        "categories": [
            {"code": "building-materials", "name": "مصالح ساختمانی", "icon": "🧱"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "building-materials", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "building-materials", "attribute": "material", "group": "مشخصات"},
            {"category": "building-materials", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "plumbing-fixtures-pipes", "name": "شیرآلات و لوله", "icon": "🚰", "sector": "industry",
        "version": 1, "display_order": 83,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های شیرآلات و لوله.",
        "categories": [
            {"code": "plumbing-fixtures-pipes", "name": "شیرآلات و لوله", "icon": "🚰"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "plumbing-fixtures-pipes", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "plumbing-fixtures-pipes", "attribute": "material", "group": "مشخصات"},
            {"category": "plumbing-fixtures-pipes", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "industrial-paint-resin", "name": "رنگ و رزین صنعتی", "icon": "🎨", "sector": "industry",
        "version": 1, "display_order": 84,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های رنگ و رزین صنعتی.",
        "categories": [
            {"code": "industrial-paint-resin", "name": "رنگ و رزین صنعتی", "icon": "🎨"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "industrial-paint-resin", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "industrial-paint-resin", "attribute": "material", "group": "مشخصات"},
            {"category": "industrial-paint-resin", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "doors-windows", "name": "در و پنجره", "icon": "🪟", "sector": "industry",
        "version": 1, "display_order": 85,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های در و پنجره.",
        "categories": [
            {"code": "doors-windows", "name": "در و پنجره", "icon": "🪟"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "doors-windows", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "doors-windows", "attribute": "material", "group": "مشخصات"},
            {"category": "doors-windows", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "industrial-tools", "name": "ابزار صنعتی", "icon": "🧰", "sector": "industry",
        "version": 1, "display_order": 86,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ابزار صنعتی.",
        "categories": [
            {"code": "industrial-tools", "name": "ابزار صنعتی", "icon": "🧰"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "industrial-tools", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "industrial-tools", "attribute": "material", "group": "مشخصات"},
            {"category": "industrial-tools", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "industrial-machinery", "name": "ماشین‌آلات صنعتی", "icon": "🏭", "sector": "industry",
        "version": 1, "display_order": 87,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های ماشین‌آلات صنعتی.",
        "categories": [
            {"code": "industrial-machinery", "name": "ماشین‌آلات صنعتی", "icon": "🏭"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "industrial-machinery", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "industrial-machinery", "attribute": "material", "group": "مشخصات"},
            {"category": "industrial-machinery", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "factory-equipment", "name": "تجهیزات کارخانه", "icon": "⚙", "sector": "industry",
        "version": 1, "display_order": 88,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های تجهیزات کارخانه.",
        "categories": [
            {"code": "factory-equipment", "name": "تجهیزات کارخانه", "icon": "⚙"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "factory-equipment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "factory-equipment", "attribute": "material", "group": "مشخصات"},
            {"category": "factory-equipment", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "industrial-safety-equipment", "name": "تجهیزات ایمنی صنعتی", "icon": "🛡", "sector": "industry",
        "version": 1, "display_order": 90,
        "description": "دسته‌بندی و ویژگی‌های توصیفیِ پایه برای فروشگاه‌های تجهیزات ایمنی صنعتی.",
        "categories": [
            {"code": "industrial-safety-equipment", "name": "تجهیزات ایمنی صنعتی", "icon": "🛡"},
        ],
        "attributes": [
            {"code": "brand", "label": "برند", "data_type": "text"},
            {"code": "material", "label": "جنس/متریال", "data_type": "text"},
            {"code": "dimensions", "label": "ابعاد", "data_type": "text"},
        ],
        "mappings": [
            {"category": "industrial-safety-equipment", "attribute": "brand", "group": "مشخصات", "filterable": True},
            {"category": "industrial-safety-equipment", "attribute": "material", "group": "مشخصات"},
            {"category": "industrial-safety-equipment", "attribute": "dimensions", "group": "مشخصات"},
        ],
    },
    {
        "slug": "printing-advertising-services", "name": "خدمات چاپ و تبلیغات", "icon": "🖨", "sector": "services",
        "version": 1, "display_order": 91,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «خدمات چاپ و تبلیغات» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "printing-advertising-services", "name": "خدمات چاپ و تبلیغات", "icon": "🖨"},
        ],
        "attributes": [],
    },
    {
        "slug": "photography-videography-services", "name": "عکاسی و فیلمبرداری", "icon": "📸", "sector": "services",
        "version": 1, "display_order": 92,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «عکاسی و فیلمبرداری» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "photography-videography-services", "name": "عکاسی و فیلمبرداری", "icon": "📸"},
        ],
        "attributes": [],
    },
    {
        "slug": "salon-beauty-services", "name": "آرایشگاه و سالن زیبایی", "icon": "💄", "sector": "services",
        "version": 1, "display_order": 93,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «آرایشگاه و سالن زیبایی» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "salon-beauty-services", "name": "آرایشگاه و سالن زیبایی", "icon": "💄"},
        ],
        "attributes": [],
    },
    {
        "slug": "restaurant-cafe", "name": "رستوران و کافه", "icon": "🍽", "sector": "services",
        "version": 1, "display_order": 94,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «رستوران و کافه» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "restaurant-cafe", "name": "رستوران و کافه", "icon": "🍽"},
        ],
        "attributes": [],
    },
    {
        "slug": "hotel-accommodation", "name": "هتل و اقامتگاه", "icon": "🏨", "sector": "services",
        "version": 1, "display_order": 95,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «هتل و اقامتگاه» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "hotel-accommodation", "name": "هتل و اقامتگاه", "icon": "🏨"},
        ],
        "attributes": [],
    },
    {
        "slug": "travel-agency", "name": "آژانس مسافرتی", "icon": "✈", "sector": "services",
        "version": 1, "display_order": 96,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «آژانس مسافرتی» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "travel-agency", "name": "آژانس مسافرتی", "icon": "✈"},
        ],
        "attributes": [],
    },
    {
        "slug": "tutoring-education-services", "name": "خدمات آموزشی و تدریس", "icon": "🎓", "sector": "services",
        "version": 1, "display_order": 97,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «خدمات آموزشی و تدریس» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "tutoring-education-services", "name": "خدمات آموزشی و تدریس", "icon": "🎓"},
        ],
        "attributes": [],
    },
    {
        "slug": "consulting-services", "name": "خدمات مشاوره", "icon": "💼", "sector": "services",
        "version": 1, "display_order": 98,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «خدمات مشاوره» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "consulting-services", "name": "خدمات مشاوره", "icon": "💼"},
        ],
        "attributes": [],
    },
    {
        "slug": "digital-design-services", "name": "خدمات دیجیتال و طراحی", "icon": "💻", "sector": "services",
        "version": 1, "display_order": 99,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «خدمات دیجیتال و طراحی» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "digital-design-services", "name": "خدمات دیجیتال و طراحی", "icon": "💻"},
        ],
        "attributes": [],
    },
    {
        "slug": "delivery-courier-services", "name": "خدمات ارسال و پیک", "icon": "🚚", "sector": "services",
        "version": 1, "display_order": 100,
        "description": "یک دسته‌بندیِ پایه برای کسب‌وکارهای «خدمات ارسال و پیک» — بدونِ ویژگیِ محصولِ فیزیکی؛ رزرو/نوبت‌دهیِ پیشرفته در نسخه‌های بعدی.",
        "categories": [
            {"code": "delivery-courier-services", "name": "خدمات ارسال و پیک", "icon": "🚚"},
        ],
        "attributes": [],
    },
]

