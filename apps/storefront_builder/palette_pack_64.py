"""Curated palette additions for RastiSi's 64+ public palette library.

Color values are adapted from the MIT-licensed UI UX Pro Max colors dataset.
Only semantic color data is carried over; RastiSi owns the palette names,
grouping and mapping into its storefront-wide appearance roles.
"""

SOURCE_REPOSITORY = "nextlevelbuilder/ui-ux-pro-max-skill"
SOURCE_DATASET = "src/ui-ux-pro-max/data/colors.csv"
SOURCE_LICENSE = "MIT"


def _entry(source_row, slug, name_fa, group_fa, primary, on_primary, secondary,
           accent, background, foreground, card, card_foreground, muted, border):
    colors = {
        "primary": primary,
        "secondary": secondary,
        "accent": accent,
        "background": background,
        "surface": card,
        "text": foreground,
        "muted": muted,
        "border": border,
    }
    return {
        "source_row": source_row,
        "slug": slug,
        "name_fa": name_fa,
        "group_fa": group_fa,
        "colors": colors,
        "theme_roles": {
            "header_bg": primary,
            "header_text": on_primary,
            "nav_bg": card,
            "nav_text": card_foreground,
            "card_bg": card,
            "footer_bg": primary,
            "footer_text": on_primary,
            "price": accent,
        },
    }


CURATED_PALETTE_PACK_64_ADDITIONS = (
    _entry(1, "uupm-trust-blue", "آبی اعتماد", "حرفه‌ای", "#2563EB", "#FFFFFF", "#3B82F6", "#EA580C", "#F8FAFC", "#1E293B", "#FFFFFF", "#1E293B", "#475569", "#E2E8F0"),
    _entry(2, "uupm-indigo-emerald", "نیلی زمردی", "حرفه‌ای", "#6366F1", "#000000", "#818CF8", "#059669", "#F5F3FF", "#1E1B4B", "#FFFFFF", "#1E1B4B", "#475569", "#E0E7FF"),
    _entry(3, "uupm-commerce-green", "سبز فروشگاهی", "فروشگاهی", "#059669", "#000000", "#10B981", "#EA580C", "#ECFDF5", "#064E3B", "#FFFFFF", "#064E3B", "#475569", "#A7F3D0"),
    _entry(5, "uupm-professional-navy", "سرمه‌ای حرفه‌ای", "حرفه‌ای", "#0F172A", "#FFFFFF", "#334155", "#0369A1", "#F8FAFC", "#020617", "#FFFFFF", "#020617", "#475569", "#E2E8F0"),
    _entry(6, "uupm-finance-night", "مالی شب", "تیره", "#0F172A", "#FFFFFF", "#1E293B", "#22C55E", "#020617", "#F8FAFC", "#0E1223", "#F8FAFC", "#94A3B8", "#334155"),
    _entry(7, "uupm-data-blue", "آبی داده", "حرفه‌ای", "#1E40AF", "#FFFFFF", "#3B82F6", "#D97706", "#F8FAFC", "#1E3A8A", "#FFFFFF", "#1E3A8A", "#475569", "#DBEAFE"),
    _entry(8, "uupm-health-cyan", "فیروزه سلامت", "آرام", "#0891B2", "#000000", "#22D3EE", "#059669", "#ECFEFF", "#164E63", "#FFFFFF", "#164E63", "#475569", "#A5F3FC"),
    _entry(10, "uupm-creative-pink", "صورتی خلاق", "خلاق", "#EC4899", "#000000", "#F472B6", "#0891B2", "#FDF2F8", "#831843", "#FFFFFF", "#831843", "#475569", "#FBCFE8"),
    _entry(11, "uupm-mono-blue", "مونو آبی", "مینیمال", "#18181B", "#FFFFFF", "#3F3F46", "#2563EB", "#FAFAFA", "#09090B", "#FFFFFF", "#09090B", "#475569", "#E4E4E7"),
    _entry(12, "uupm-gaming-neon", "بنفش نئون", "نئونی", "#7C3AED", "#FFFFFF", "#A78BFA", "#F43F5E", "#0F0F23", "#E2E8F0", "#1E1C35", "#E2E8F0", "#94A3B8", "#4C1D95"),
    _entry(14, "uupm-gold-purple-tech", "طلایی تکنولوژی", "لوکس", "#F59E0B", "#0F172A", "#FBBF24", "#8B5CF6", "#0F172A", "#F8FAFC", "#222735", "#F8FAFC", "#94A3B8", "#334155"),
    _entry(15, "uupm-social-rose", "رز اجتماعی", "شاد", "#E11D48", "#FFFFFF", "#FB7185", "#2563EB", "#FFF1F2", "#881337", "#FFFFFF", "#881337", "#475569", "#FECDD3"),
    _entry(16, "uupm-focus-teal", "سبزآبی تمرکز", "مدرن", "#0D9488", "#000000", "#14B8A6", "#EA580C", "#F0FDFA", "#134E4A", "#FFFFFF", "#134E4A", "#475569", "#99F6E4"),
    _entry(18, "uupm-ai-purple", "بنفش هوشمند", "نئونی", "#7C3AED", "#FFFFFF", "#A78BFA", "#0891B2", "#FAF5FF", "#1E1B4B", "#FFFFFF", "#1E1B4B", "#475569", "#DDD6FE"),
    _entry(19, "uupm-purple-gold-night", "بنفش طلایی شب", "لوکس", "#8B5CF6", "#000000", "#A78BFA", "#FBBF24", "#0F0F23", "#F8FAFC", "#1E1D35", "#F8FAFC", "#94A3B8", "#4C1D95"),
    _entry(23, "uupm-playful-orange", "نارنجی بازیگوش", "شاد", "#F97316", "#0F172A", "#FB923C", "#2563EB", "#FFF7ED", "#9A3412", "#FFFFFF", "#9A3412", "#475569", "#FED7AA"),
    _entry(24, "uupm-smart-night", "خانه هوشمند شب", "تیره", "#1E293B", "#FFFFFF", "#334155", "#22C55E", "#0F172A", "#F8FAFC", "#1B2336", "#F8FAFC", "#94A3B8", "#475569"),
    _entry(26, "uupm-magenta-energy", "ارغوانی انرژی", "شاد", "#D946EF", "#000000", "#E879F9", "#EA580C", "#FDF4FF", "#86198F", "#FFFFFF", "#86198F", "#475569", "#F5D0FE"),
    _entry(27, "uupm-midnight-audio", "صدای نیمه‌شب", "تیره", "#1E1B4B", "#FFFFFF", "#312E81", "#F97316", "#0F0F23", "#F8FAFC", "#1B1B30", "#F8FAFC", "#94A3B8", "#4338CA"),
    _entry(32, "uupm-spa-pink", "صورتی اسپا", "زیبایی", "#EC4899", "#000000", "#F9A8D4", "#8B5CF6", "#FDF2F8", "#831843", "#FFFFFF", "#831843", "#475569", "#FBCFE8"),
    _entry(34, "uupm-food-red-gold", "قرمز زعفرانی", "گرم", "#DC2626", "#FFFFFF", "#F87171", "#A16207", "#FEF2F2", "#450A0A", "#FFFFFF", "#450A0A", "#475569", "#FECACA"),
    _entry(35, "uupm-fitness-energy", "نارنجی انرژی", "انرژی", "#F97316", "#0F172A", "#FB923C", "#22C55E", "#1F2937", "#F8FAFC", "#313742", "#F8FAFC", "#CBD5E1", "#374151"),
    _entry(37, "uupm-travel-sky", "آبی سفر", "سرد", "#0EA5E9", "#0F172A", "#38BDF8", "#EA580C", "#F0F9FF", "#0C4A6E", "#FFFFFF", "#0C4A6E", "#475569", "#BAE6FD"),
    _entry(53, "uupm-photo-mono", "مونو عکاسی", "مینیمال", "#18181B", "#FFFFFF", "#27272A", "#F8FAFC", "#000000", "#FAFAFA", "#0C0C0C", "#FAFAFA", "#94A3B8", "#3F3F46"),
    _entry(63, "uupm-bakery-cream", "قهوه و کرم", "گرم", "#92400E", "#FFFFFF", "#B45309", "#92400E", "#FEF3C7", "#78350F", "#FFFFFF", "#78350F", "#475569", "#FDE68A"),
    _entry(64, "uupm-burgundy-gold", "زرشکی کلاسیک", "لوکس", "#7C2D12", "#FFFFFF", "#B91C1C", "#A16207", "#FEF2F2", "#450A0A", "#FFFFFF", "#450A0A", "#475569", "#FECACA"),
)
