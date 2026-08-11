"""Publicly-observed KianStock-like QA catalogue facts.

This module intentionally contains only short public catalogue facts such as
product/category/brand names and displayed prices. It does not contain copied
product descriptions, photographs, testimonials, or long-form site copy.
"""

TOP_CATEGORIES = [
    {"name": "پوشاک زنانه", "slug": "women", "icon": "♀", "children": [
        ("پیراهن زنانه", "women-dress"), ("شومیز", "women-blouse"),
        ("تیشرت زنانه", "women-tshirt"), ("دورس زنانه", "women-sweatshirt"),
        ("سویشرت زنانه", "women-sweatshirt-zip"), ("بافت زنانه", "women-knit"),
        ("شلوار زنانه", "women-pants"), ("شلوارک زنانه", "women-shorts"),
        ("کت زنانه", "women-jacket"), ("هودی زنانه", "women-hoodie"),
        ("تاپ و کراپ زنانه", "women-top"), ("دامن زنانه", "women-skirt"),
    ]},
    {"name": "پوشاک مردانه", "slug": "men", "icon": "♂", "children": [
        ("شلوار مردانه", "men-pants"), ("پیراهن مردانه", "men-shirt"),
        ("تیشرت مردانه", "men-tshirt"), ("پلوشرت مردانه", "men-polo"),
        ("دورس مردانه", "men-sweatshirt"), ("هودی مردانه", "men-hoodie"),
        ("بافت مردانه", "men-knit"), ("کت مردانه", "men-jacket"),
        ("کاپشن مردانه", "men-coat"), ("وست مردانه", "men-vest"),
    ]},
    {"name": "پوشاک بچگانه", "slug": "kids", "icon": "★", "children": [
        ("سارافون بچگانه", "kids-pinafore"), ("شومیز بچگانه", "kids-blouse"),
        ("ست بچگانه", "kids-set"), ("تیشرت بچگانه", "kids-tshirt"),
        ("شلوار بچگانه", "kids-pants"), ("کفش بچگانه", "kids-shoes"),
    ]},
    {"name": "پوشاک ورزشی", "slug": "sports", "icon": "⚡", "children": [
        ("ورزشی زنانه", "sports-women"), ("ورزشی مردانه", "sports-men"),
        ("ساک و کوله ورزشی", "sports-bag"), ("لگ و بایکر", "sports-legging"),
    ]},
    {"name": "عطر و ادکلن", "slug": "perfume", "icon": "◇", "children": [
        ("Amouage", "perfume-amouage"), ("Marly", "perfume-marly"),
        ("Creed", "perfume-creed"), ("Yves Saint Laurent", "perfume-ysl"),
        ("Dolce&Gabbana", "perfume-dg"), ("Tiziana Terenzi", "perfume-tiziana"),
    ]},
    {"name": "کتونی اورجینال", "slug": "sneakers", "icon": "◒", "children": [
        ("Puma Sneakers", "sneakers-puma"), ("Converse Sneakers", "sneakers-converse"),
        ("Adidas Sneakers", "sneakers-adidas"), ("Nike Sneakers", "sneakers-nike"),
        ("Reebok Sneakers", "sneakers-reebok"), ("Asics Sneakers", "sneakers-asics"),
    ]},
    {"name": "کفش و بوت و صندل", "slug": "footwear", "icon": "◢", "children": [
        ("صندل زنانه", "footwear-sandal"), ("بوت زنانه", "footwear-boots"),
        ("کراکس", "footwear-crocs"), ("کفش روزمره", "footwear-casual"),
    ]},
    {"name": "عینک آفتابی اورجینال", "slug": "sunglasses", "icon": "∞", "children": [
        ("عینک مون بلان", "glasses-montblanc"), ("عینک سلین", "glasses-celine"),
        ("عینک لاکوست", "glasses-lacoste"), ("عینک تامی هیلفیگر", "glasses-tommy"),
        ("عینک تاش", "glasses-tash"), ("سایر عینک‌ها", "glasses-other"),
    ]},
    {"name": "اکسسوری زنانه و مردانه", "slug": "accessories", "icon": "+", "children": [
        ("کیف زنانه", "accessories-bag"), ("کلاه", "accessories-hat"),
        ("شال و روسری", "accessories-scarf"), ("کمربند", "accessories-belt"),
        ("کوله", "accessories-backpack"),
    ]},
    {"name": "اوتلت ایراد دار", "slug": "outlet", "icon": "%", "children": [
        ("اوتلت پوشاک", "outlet-clothing"), ("اوتلت کفش", "outlet-footwear"),
    ]},
]

BRANDS = [
    ("Adidas", "adidas"), ("Puma", "puma"), ("Converse", "converse"),
    ("Nike", "nike"), ("Reebok", "reebok"), ("Zara", "zara"),
    ("H&M", "hm"), ("Levi's", "levis"), ("Jack & Jones", "jack-jones"),
    ("S.Oliver", "s-oliver"), ("The North Face", "north-face"),
    ("Selected", "selected"), ("Buffalo", "buffalo"), ("Esmara", "esmara"),
    ("Crane", "crane"), ("Longchamp", "longchamp"),
    ("Mont Blanc", "montblanc"), ("Celine", "celine"), ("Lacoste", "lacoste"),
    ("Tommy Hilfiger", "tommy-hilfiger"), ("Amouage", "amouage"),
    ("Marly", "marly"), ("Creed", "creed"), ("Yves Saint Laurent", "ysl"),
    ("Dolce&Gabbana", "dolce-gabbana"), ("Tiziana Terenzi", "tiziana-terenzi"),
    ("Benetton", "benetton"), ("Only & Sons", "only-sons"),
    ("Lululemon", "lululemon"), ("Generic Stock", "generic-stock"),
]

# collection slug, category slug, brand slug, product title, displayed/current price,
# regular/original price (None when not discounted)
PRODUCTS = [
    # 01 — sale row
    ("sale", "kids-pinafore", "generic-stock", "سارافون گل گلی بچگانه", 550000, 750000),
    ("sale", "kids-pinafore", "generic-stock", "سارافون بچگانه آستین گلدوزی", 1650000, 1890000),
    ("sale", "women-dress", "generic-stock", "تونیک زنانه کره ای اورو سایهٔ مشکی سئول", 980000, 1750000),
    ("sale", "women-blouse", "generic-stock", "شومیز مانتویی ۴خونه سورمه ای tilley", 1180000, 1820000),
    ("sale", "kids-blouse", "generic-stock", "شومیز کراپ بچگانه پلنگی سبز", 1450000, 1630000),
    ("sale", "men-shirt", "generic-stock", "پیراهن لینن پفکی قهوه ای سوخته اسموگ", 1420000, 1920000),
    ("sale", "women-hoodie", "generic-stock", "هودی کراپ ایکس صورتی خاکی", 1750000, 2490000),
    ("sale", "sports-women", "generic-stock", "اسلش سبز تیره حرفه ای موندیتا", 550000, 735000),
    ("sale", "kids-shoes", "generic-stock", "صندل بچگانه چسبی اسپایدرمن", 1300000, 1500000),
    ("sale", "women-tshirt", "generic-stock", "ست تیشرت و شلوارک تیفانی", 1720000, 1820000),
    # 02 — newest
    ("newest", "men-pants", "generic-stock", "شلوار چینو کرم استخوانی", 2450000, None),
    ("newest", "men-pants", "adidas", "شلوار مردانه گلف خاکی آدیداس", 6900000, None),
    ("newest", "men-pants", "generic-stock", "شلوار جین راسته آبی سنگشور پلمبیر", 1850000, None),
    ("newest", "men-pants", "hm", "شلوار مردانه سورمه ای اچ اند ام", 1150000, None),
    ("newest", "men-pants", "generic-stock", "شلوار جین راسته اسیدواش سنگشور", 1900000, None),
    ("newest", "men-pants", "levis", "شلوار مردانه ابروبادی لیوایز", 1350000, None),
    ("newest", "men-pants", "generic-stock", "شلوار جین سورمه ای تیره زاپ دار", 1100000, None),
    ("newest", "men-pants", "generic-stock", "شلوار جاگر اوربان گایام", 1850000, None),
    ("newest", "men-pants", "generic-stock", "شلوار مردانه کتان مشکی", 1650000, None),
    ("newest", "men-pants", "generic-stock", "شلوار مردانه داخل پلاری سورمه ای", 2200000, None),
    # 03 — sneakers
    ("sneakers", "sneakers-converse", "converse", "کتونی کانورس ساقدار سفید chuck70", 4550000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Flyer", 10800000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma St Runner مشکی خط سفید", 11300000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Caracal", 11800000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Nitro Elite 2", 22800000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Nitro Elite 2 WNS", 22800000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma SOFTRIDE Sophia", 9440000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Maxima Pro", 14960000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma caracal سفید خط ماتیکی", 11392000, None),
    ("sneakers", "sneakers-puma", "puma", "کتونی پو.ما مدل Puma Carina Street Jr", 12272000, None),
    # 04 — sunglasses
    ("sunglasses", "glasses-montblanc", "montblanc", "عینک مشکی مون بلانmb-0320", 9900000, None),
    ("sunglasses", "glasses-celine", "celine", "عینک سلین cl-40293 سیلور آبی", 9450000, None),
    ("sunglasses", "glasses-lacoste", "lacoste", "عینک لاکوست la-21311 t قهوه ای", 5350000, None),
    ("sunglasses", "glasses-tommy", "tommy-hilfiger", "عینک تامی th-2052 هاوانا", 9750000, None),
    ("sunglasses", "glasses-other", "generic-stock", "عینک x10-d فسفری شفاف", 6550000, None),
    ("sunglasses", "glasses-tommy", "tommy-hilfiger", "عینک تامی th-1976 هاوانا", 9750000, None),
    ("sunglasses", "glasses-montblanc", "montblanc", "عینک مون بلان mb-0258 طوسی شفاف", 10450000, None),
    ("sunglasses", "glasses-other", "generic-stock", "عینک x10-d فسفری", 6550000, None),
    ("sunglasses", "glasses-tash", "generic-stock", "عینک فریم فلزی to/sh", 490000, None),
    ("sunglasses", "glasses-tommy", "tommy-hilfiger", "عینک تامی th-2052 مشکی", 9750000, None),
    # 05 — perfume
    ("perfume", "perfume-amouage", "amouage", "عطر آمواج سیکوئنس | Amouage Sequence", 6520000, None),
    ("perfume", "perfume-amouage", "amouage", "عطر آمواج ریماین | Amouage Remain", 6520000, None),
    ("perfume", "perfume-amouage", "amouage", "عطر آمواج لاین | Amouage Line 618", 6520000, None),
    ("perfume", "perfume-marly", "marly", "عطر مارلی آتنایس | Marly Athenais", 5980000, None),
    ("perfume", "perfume-creed", "creed", "عطر کرید ویرجین آیلند واتر – Creed Virgin Island Water", 5820000, None),
    ("perfume", "perfume-ysl", "ysl", "عطر لیبر بری کراش ایو سن لورن | Yves Saint Laurent Libre Berry Crush", 5820000, None),
    ("perfume", "perfume-amouage", "amouage", "عطر آمواج ایمیتیشن زنانه | Amouage Imitation Woman", 6520000, None),
    ("perfume", "perfume-dg", "dolce-gabbana", "عطر دولچه اند گابانا کی | Dolce & Gabbana K", 5820000, None),
    ("perfume", "perfume-marly", "marly", "عطر مارلی سدلی – Parfums de Marly Sedley", 6120000, None),
    ("perfume", "perfume-tiziana", "tiziana-terenzi", "عطر تیزیانا ترنزی کیرکه | Tiziana Terenzi Kirke Extrait de Parfum", 6220000, None),
    # 06 — women
    ("women", "women-dress", "generic-stock", "پیراهن ماکسی طرح گل آبی زنانه", 1720000, None),
    ("women", "women-dress", "generic-stock", "پیراهن ماکسی طرح گل مشکی زنانه", 1720000, None),
    ("women", "women-blouse", "zara", "شومیز کرم شیشه ای زارا", 1950000, None),
    ("women", "women-blouse", "zara", "شومیز آبی شیشه ای زارا", 1950000, None),
    ("women", "women-blouse", "zara", "شومیز صورتی شیشه ای زارا", 1950000, None),
    ("women", "women-tshirt", "generic-stock", "پلوشرت یاسی زنانه دو دکمه انلی سانس", 1690000, None),
    ("women", "women-tshirt", "generic-stock", "پلوشرت صورتی کم رنگ لوگو سفید انلی سانس", 1730000, None),
    ("women", "women-sweatshirt", "generic-stock", "دورس کرم شیری پلمبیر", 2650000, None),
    ("women", "women-sweatshirt", "generic-stock", "دورس خردلی", 1850000, None),
    ("women", "women-sweatshirt", "jack-jones", "دورس آبی جک جونز نوشته قرمز", 1860000, None),
    # 07 — footwear
    ("footwear", "footwear-sandal", "generic-stock", "سندل انگشتی پلنگی", 995000, None),
    ("footwear", "footwear-crocs", "esmara", "کراکس سورمه ای خز دار زنانه اسمارا", 2350000, None),
    ("footwear", "footwear-sandal", "generic-stock", "صندل بندی کف تخت آبی وات لوس", 1350000, None),
    ("footwear", "footwear-crocs", "crane", "کراکس مشکی پشت طوسی crane", 1950000, None),
    ("footwear", "footwear-boots", "generic-stock", "بوت مدل چلسی چرمی", 3490000, None),
    ("footwear", "footwear-sandal", "generic-stock", "صندل کف تخته ای حصیری قهوه ای لژ دار آلما.نی", 2340000, None),
    ("footwear", "footwear-boots", "generic-stock", "بوت مدل کامبت بند دار", 3790000, None),
    ("footwear", "footwear-crocs", "esmara", "کراکس خز دار زنانه اسمارا", 2350000, None),
    ("footwear", "footwear-boots", "generic-stock", "نیم بوت چلسی پاشنه دار صورتی", 2850000, None),
    ("footwear", "footwear-boots", "generic-stock", "بوت چرمی بلند", 3850000, None),
    # 08 — men
    ("men", "men-coat", "north-face", "کاپشن نورث فیس مشکی سورمه ای", 8950000, None),
    ("men", "men-pants", "generic-stock", "جاگر طوسی کرکی GYM", 2150000, None),
    ("men", "men-jacket", "selected", "کت اسلیم فیت مشکی سلکتد", 3200000, None),
    ("men", "men-knit", "buffalo", "بافت ضخیم مردانه طرح کلاسیک و لوزی بوفالو", 1980000, None),
    ("men", "men-shirt", "generic-stock", "پیراهن مردانه آستین بلند طرح هندسی ریز سورمه‌ای", 1250000, None),
    ("men", "men-tshirt", "generic-stock", "تیشرت سفید لوگو‌ مشکی فور اف", 1450000, None),
    ("men", "men-shirt", "generic-stock", "پیراهن مردانه آستین بلند چهارخانه قرمز و سفید", 965000, None),
    ("men", "men-tshirt", "generic-stock", "تیشرت گرم بالا سنگشور داب", 1980000, None),
    ("men", "men-tshirt", "generic-stock", "تنگ تاپ مشکی بلژیکی", 1180000, None),
    ("men", "men-jacket", "generic-stock", "کت تک مردانه مدل رادن مشکی", 3240000, None),
    # 09 — sports / mixed athletic row
    ("sports", "women-knit", "generic-stock", "پلیور بافت یقه شل (Cowl Neck) زنانه کرم", 1720000, None),
    ("sports", "women-blouse", "s-oliver", "شومیز کرپ حریر اس اولیور وافل", 1820000, None),
    ("sports", "sports-women", "generic-stock", "پیراهن ورزشی حرفه ای سبزآبی lo.le", 2450000, None),
    ("sports", "sports-women", "generic-stock", "شلوارک زنانه راه راه آبی لوگو قلبی", 950000, None),
    ("sports", "women-dress", "generic-stock", "پیراهن سفید مانتویی کتان", 1350000, None),
    ("sports", "women-sweatshirt-zip", "generic-stock", "سویشرت مشکی لوگو بنفش", 2650000, None),
    ("sports", "men-sweatshirt", "only-sons", "نیم زیپ ریز بافت ماسه ای روشن only&sons", 1790000, None),
    ("sports", "women-dress", "generic-stock", "تونیک زنانه کره ای مدل هانوال سبز لجنی", 1690000, None),
    ("sports", "women-dress", "generic-stock", "پیراهن مانتویی کبریتی سفید شیری", 1780000, None),
    ("sports", "women-dress", "generic-stock", "پیراهن راه راه سفید مشکی چپس", 1650000, None),
    # 10 — accessories
    ("accessories", "accessories-bag", "longchamp", "کیف برزنتی اسمال لانگ‌ چمپ پسته ای", 8250000, None),
    ("accessories", "accessories-hat", "generic-stock", "کلاه ابی مشکی", 880000, None),
    ("accessories", "accessories-bag", "longchamp", "کیف استخوانی دو اندازه لانگ چمپ", 9850000, None),
    ("accessories", "accessories-scarf", "s-oliver", "شال حلقه ای سبز سولیور", 1280000, None),
    ("accessories", "accessories-backpack", "generic-stock", "کوله راکت تنیس حرفه ای wish نارنجی لیزری", 5250000, None),
    ("accessories", "accessories-hat", "generic-stock", "کلاه طوسی خاکستری cerci", 880000, None),
    ("accessories", "accessories-bag", "longchamp", "کیف مشکی دو اندازه لانگ چمپ", 9850000, None),
    ("accessories", "accessories-belt", "s-oliver", "کمربند زنانه مشکی soliver", 1980000, None),
    ("accessories", "accessories-bag", "longchamp", "کیف شکلاتی سوخته دو اندازه لانگ چمپ", 9850000, None),
    ("accessories", "accessories-scarf", "s-oliver", "شال گردنی و روسری حلقه ای اس اولیور", 1550000, None),
]

COLLECTIONS = [
    ("sale", "تخفیفات شگفت انگیز"),
    ("newest", "جدید ترین محصولات"),
    ("sneakers", "کفش و کتونی اورجینال"),
    ("sunglasses", "عینک آفتابی اورجینال"),
    ("perfume", "عطر و ادکلن"),
    ("women", "پوشاک زنانه"),
    ("footwear", "کفش و بوت و صندل"),
    ("men", "پوشاک مردانه"),
    ("sports", "پوشاک ورزشی"),
    ("accessories", "اکسسوری"),
]

assert len(PRODUCTS) == 100
