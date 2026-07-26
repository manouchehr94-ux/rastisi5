import re
from decimal import Decimal, InvalidOperation

from django import forms

from apps.catalog.models import Category, Product
from apps.core.color_utils import contrast_ratio, safe_hex
from apps.core.models import ShopSettings
from apps.core.utils import normalize_digits
from apps.sms.services.sms_service import SmsTemplateError, validate_template_body

from .services.catalog_admin_service import leaf_categories

PHONE_RE = re.compile(r"^09\d{9}$")


class NumericCleanMixin:
    """نرمال‌سازی ارقام فارسی/عربی به لاتین پیش از تبدیل به عدد — مثل بقیه‌ی فرم‌های سایت."""

    def _clean_int(self, field_name, *, min_value=None, max_value=None):
        raw = normalize_digits(self.cleaned_data.get(field_name, "")).strip()
        if raw == "":
            raise forms.ValidationError("این فیلد الزامی است")
        try:
            value = int(raw)
        except ValueError:
            raise forms.ValidationError("باید یک عدد صحیح باشد")
        if min_value is not None and value < min_value:
            raise forms.ValidationError(f"باید حداقل {min_value} باشد")
        if max_value is not None and value > max_value:
            raise forms.ValidationError(f"باید حداکثر {max_value} باشد")
        return value

    def _clean_decimal(self, field_name, *, min_value=None, max_value=None):
        raw = normalize_digits(self.cleaned_data.get(field_name, "")).strip()
        if raw == "":
            raise forms.ValidationError("این فیلد الزامی است")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise forms.ValidationError("باید یک عدد باشد")
        if min_value is not None and value < min_value:
            raise forms.ValidationError(f"باید حداقل {min_value} باشد")
        if max_value is not None and value > max_value:
            raise forms.ValidationError(f"باید حداکثر {max_value} باشد")
        return value


class ProductForm(NumericCleanMixin, forms.Form):
    STATUS_CHOICES = [
        (Product.Status.ACTIVE, "فعال"),
        (Product.Status.INACTIVE, "غیرفعال"),
    ]

    name = forms.CharField(label="نام کالا", max_length=220)
    sku = forms.CharField(label="کد کالا (SKU)", max_length=40)
    category = forms.ModelChoiceField(
        label="زیرگروه کالا", queryset=Category.objects.none(),
        error_messages={"required": "انتخاب زیرگروه الزامی است"},
    )
    price = forms.CharField(label="قیمت (تومان)")
    discount_percent = forms.CharField(label="تخفیف (٪)", required=False, initial="0")
    stock = forms.CharField(label="موجودی انبار", required=False, initial="0")
    status = forms.ChoiceField(label="وضعیت", choices=STATUS_CHOICES, initial=Product.Status.ACTIVE)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)
    description = forms.CharField(label="توضیحات کوتاه", widget=forms.Textarea, required=False)
    # اختیاری است تا فرم‌های قدیمی/تست‌هایی که این فیلد را ارسال نمی‌کنند همچنان کار کنند؛
    # وقتی خالی باشد یعنی «نوع کالا تغییر نکند» و از سرویس گذار نوع کالا استفاده نمی‌شود.
    product_type = forms.ChoiceField(
        label="نوع کالا", choices=Product.ProductType.choices, required=False,
    )

    def __init__(self, *args, store, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.store = store
        self.fields["category"].queryset = leaf_categories(store)

    def clean_sku(self):
        sku = normalize_digits(self.cleaned_data["sku"]).strip()
        if not sku:
            raise forms.ValidationError("کد کالا الزامی است")
        qs = Product.objects.filter(store=self.store, sku=sku)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این کد کالا قبلاً استفاده شده است")
        return sku

    def clean_category(self):
        category = self.cleaned_data["category"]
        if category.store_id != self.store.pk:
            raise forms.ValidationError("این دسته‌بندی متعلق به فروشگاه دیگری است")
        return category

    def clean_price(self):
        return self._clean_int("price", min_value=1)

    def clean_discount_percent(self):
        if not self.data.get("discount_percent", "").strip():
            return 0
        return self._clean_int("discount_percent", min_value=0, max_value=100)

    def clean_stock(self):
        if not self.data.get("stock", "").strip():
            return 0
        return self._clean_int("stock", min_value=0)


class VariantBulkAddForm(NumericCleanMixin, forms.Form):
    """اعتبارسنجی ساختاری ورودی سریع تنوع؛ تجزیه و اعتبارسنجی کسب‌وکاری در سرویس تنوع انجام می‌شود."""

    attribute = forms.CharField(label="نام تنوع", max_length=60, help_text="مثلاً: رنگ، سایز، حجم، مدل")
    raw_values = forms.CharField(
        label="مقادیر تنوع", widget=forms.Textarea,
        help_text="هر مقدار را در یک خط، یا با کاما/سمیکالن از هم جدا کنید.",
    )
    default_stock = forms.CharField(label="موجودی پیش‌فرض", required=False, initial="0")
    default_extra_price = forms.CharField(label="تغییر قیمت پیش‌فرض (تومان)", required=False, initial="0")
    is_active = forms.BooleanField(label="فعال باشند", required=False, initial=True)

    def clean_attribute(self):
        attribute = self.cleaned_data["attribute"].strip()
        if not attribute:
            raise forms.ValidationError("نام تنوع نمی‌تواند خالی باشد")
        return attribute

    def clean_default_stock(self):
        if not self.data.get("default_stock", "").strip():
            return 0
        return self._clean_int("default_stock", min_value=0)

    def clean_default_extra_price(self):
        if not self.data.get("default_extra_price", "").strip():
            return 0
        return self._clean_decimal("default_extra_price")


class VariantEditForm(NumericCleanMixin, forms.Form):
    """اعتبارسنجی ساختاری ویرایش یک مقدار تنوع؛ یکتایی و نرمال‌سازی در سرویس تنوع انجام می‌شود."""

    attribute = forms.CharField(label="نام تنوع", max_length=60)
    value = forms.CharField(label="مقدار تنوع", max_length=60)
    sku = forms.CharField(label="کد کالا (SKU)", max_length=64, required=False)
    extra_price = forms.CharField(label="تغییر قیمت (تومان)", required=False, initial="0")
    stock = forms.CharField(label="موجودی", required=False, initial="0")
    is_active = forms.BooleanField(label="فعال", required=False)

    def clean_attribute(self):
        attribute = self.cleaned_data["attribute"].strip()
        if not attribute:
            raise forms.ValidationError("نام تنوع نمی‌تواند خالی باشد")
        return attribute

    def clean_value(self):
        value = self.cleaned_data["value"].strip()
        if not value:
            raise forms.ValidationError("مقدار تنوع نمی‌تواند خالی باشد")
        return value

    def clean_extra_price(self):
        if not self.data.get("extra_price", "").strip():
            return 0
        return self._clean_decimal("extra_price")

    def clean_stock(self):
        if not self.data.get("stock", "").strip():
            return 0
        return self._clean_int("stock", min_value=0)


class MainCategoryForm(forms.Form):
    name = forms.CharField(label="نام گروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False, initial="📁")


class SubCategoryForm(forms.Form):
    parent = forms.ModelChoiceField(
        label="گروه والد", queryset=Category.objects.none(),
        error_messages={"required": "انتخاب گروه والد الزامی است"},
    )
    name = forms.CharField(label="نام زیرگروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(
            store=store, parent__isnull=True
        ).order_by("order", "name")


class CategoryEditForm(forms.Form):
    name = forms.CharField(label="نام", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)


class ShopInfoForm(forms.Form):
    name = forms.CharField(label="نام فروشگاه", max_length=150, widget=forms.TextInput(attrs={"class": "inp"}))
    tagline = forms.CharField(
        label="شعار فروشگاه", max_length=200, required=False, widget=forms.TextInput(attrs={"class": "inp"})
    )
    contact_phone = forms.CharField(
        label="شماره تماس", max_length=30, required=False,
        widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"}),
    )
    contact_email = forms.EmailField(
        label="ایمیل فروشگاه", required=False, widget=forms.EmailInput(attrs={"class": "inp", "dir": "ltr"})
    )
    contact_address = forms.CharField(
        label="آدرس", max_length=300, required=False,
        widget=forms.Textarea(attrs={"class": "inp", "rows": 2}),
    )
    description = forms.CharField(
        label="توضیحات فروشگاه", required=False, widget=forms.Textarea(attrs={"class": "inp", "rows": 3})
    )


class FinanceSettingsForm(NumericCleanMixin, forms.Form):
    tax_percent = forms.CharField(label="نرخ مالیات (٪)", widget=forms.TextInput(attrs={"class": "inp"}))
    free_shipping_threshold = forms.CharField(
        label="آستانه‌ی ارسال رایگان (تومان)", widget=forms.TextInput(attrs={"class": "inp"})
    )

    def clean_tax_percent(self):
        return self._clean_decimal("tax_percent", min_value=0, max_value=100)

    def clean_free_shipping_threshold(self):
        return self._clean_int("free_shipping_threshold", min_value=0)


class SmsConnectionForm(forms.Form):
    sms_enabled = forms.BooleanField(label="فعال‌سازی سیستم پیامک", required=False)
    sms_backend = forms.ChoiceField(
        label="درگاه پیامک", choices=ShopSettings.SmsBackend.choices, widget=forms.Select(attrs={"class": "inp"})
    )
    sms_sender_number = forms.CharField(
        label="شماره‌ی فرستنده", max_length=20, required=False, widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"})
    )
    melipayamak_username = forms.CharField(
        label="نام کاربری ملی‌پیامک", max_length=100, required=False,
        widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"}),
    )
    melipayamak_password = forms.CharField(
        label="رمز عبور ملی‌پیامک", max_length=100, required=False,
        widget=forms.PasswordInput(attrs={"class": "inp", "dir": "ltr"}, render_value=True),
    )


class SmsTemplateForm(forms.Form):
    body = forms.CharField(label="متن قالب", widget=forms.Textarea(attrs={"class": "inp", "rows": 4}))

    def __init__(self, *args, event_key=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_key = event_key

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        try:
            validate_template_body(self.event_key, body)
        except SmsTemplateError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return body
        return body


class SmsTestForm(forms.Form):
    phone = forms.CharField(label="شماره موبایل گیرنده‌ی آزمایشی", max_length=15, widget=forms.TextInput(attrs={"class": "inp", "dir": "ltr"}))

    def clean_phone(self):
        phone = normalize_digits(self.cleaned_data["phone"]).strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("شماره موبایل معتبر نیست (مثال: 09123456789)")
        return phone


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiImageField(forms.FileField):
    """فیلد آپلود چندتایی — الگوی مستندشده‌ی Django برای FileField چندفایلی."""

    widget = MultiFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return single_file_clean(data, initial)


class ProductImageUploadForm(forms.Form):
    images = MultiImageField(
        label="تصاویر", required=False, widget=MultiFileInput(attrs={"multiple": True, "accept": ".jpg,.jpeg,.png,.webp"})
    )


class ProductImageAltForm(forms.Form):
    alt = forms.CharField(label="متن جایگزین", max_length=200, required=False)



# --- هویت بصری ---

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_FAVICON_TYPES = {"image/png", "image/x-icon", "image/vnd.microsoft.icon"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_FAVICON_SIZE = 512 * 1024  # 512 KB


def _validate_hex_color(value):
    """اعتبارسنجی رنگ هگزادسیمال #RRGGBB — فقط مقادیر امن."""
    value = value.strip()
    if not HEX_COLOR_RE.match(value):
        raise forms.ValidationError("رنگ باید به فرمت #RRGGBB باشد (مثال: #6D28D9)")
    return value.upper()


def _validate_image_upload(file, allowed_types, max_size, label):
    """اعتبارسنجی فایل تصویر: نوع، اندازه، و محتوای واقعی."""
    if file.size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise forms.ValidationError(f"حجم {label} نباید بیشتر از {max_mb:.0f} مگابایت باشد")

    if file.content_type not in allowed_types:
        raise forms.ValidationError(f"فرمت {label} معتبر نیست. فرمت‌های مجاز: PNG, JPEG, WebP")

    # Verify actual image content
    try:
        from PIL import Image
        img = Image.open(file)
        img.verify()
        file.seek(0)
    except Exception:
        raise forms.ValidationError(f"فایل {label} یک تصویر معتبر نیست")

    return file


def _color_field(label, required=False):
    return forms.CharField(
        label=label, max_length=7, required=required,
        widget=forms.TextInput(attrs={"class": "inp", "type": "color", "style": "width:60px;height:40px;padding:4px"}),
    )


class VisualIdentityForm(forms.Form):
    """فرم هویت بصری فروشگاه: لوگو، فاوآیکون و توکن‌های رنگی تم.

    ``primary_color``/``accent_color`` همیشه اجباری‌اند (سازگاری با فرم قدیمی).
    توکن‌های جدید تم (ثانویه، پس‌زمینه، سطح، متن، متن کم‌رنگ) اختیاری‌اند — اگر
    ارسال نشوند، مقدار فعلی/پیش‌فرض فروشگاه دست‌نخورده می‌ماند (view تصمیم می‌گیرد).
    """

    logo = forms.ImageField(label="لوگوی فروشگاه", required=False)
    remove_logo = forms.BooleanField(label="حذف لوگوی فعلی", required=False)

    favicon = forms.ImageField(label="فاوآیکون", required=False)
    remove_favicon = forms.BooleanField(label="حذف فاوآیکون فعلی", required=False)

    primary_color = _color_field("رنگ اصلی", required=True)
    accent_color = _color_field("رنگ مکمل", required=True)
    secondary_color = _color_field("رنگ ثانویه")
    background_color = _color_field("رنگ پس‌زمینه‌ی صفحه")
    surface_color = _color_field("رنگ پس‌زمینه‌ی کارت‌ها")
    text_color = _color_field("رنگ متن اصلی")
    muted_text_color = _color_field("رنگ متن کم‌رنگ")

    def __init__(self, *args, current_shop=None, **kwargs):
        """``current_shop`` مقادیر فعلیِ فیلدهای ارسال‌نشده را برای بررسی کنتراست کامل می‌کند."""
        self._current_shop = current_shop
        super().__init__(*args, **kwargs)

    def clean_primary_color(self):
        return _validate_hex_color(self.cleaned_data["primary_color"])

    def clean_accent_color(self):
        return _validate_hex_color(self.cleaned_data["accent_color"])

    def _clean_optional_color(self, field_name):
        value = self.cleaned_data.get(field_name, "").strip()
        if not value:
            return ""
        return _validate_hex_color(value)

    def clean_secondary_color(self):
        return self._clean_optional_color("secondary_color")

    def clean_background_color(self):
        return self._clean_optional_color("background_color")

    def clean_surface_color(self):
        return self._clean_optional_color("surface_color")

    def clean_text_color(self):
        return self._clean_optional_color("text_color")

    def clean_muted_text_color(self):
        return self._clean_optional_color("muted_text_color")

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo:
            return _validate_image_upload(logo, ALLOWED_LOGO_TYPES, MAX_LOGO_SIZE, "لوگو")
        return logo

    def clean_favicon(self):
        favicon = self.cleaned_data.get("favicon")
        if favicon:
            return _validate_image_upload(favicon, ALLOWED_FAVICON_TYPES, MAX_FAVICON_SIZE, "فاوآیکون")
        return favicon

    def clean(self):
        """کنتراست متن اصلی/کم‌رنگ در برابر پس‌زمینه و سطح را روی ترکیب نهایی (نه فقط فیلدهای تازه) بررسی می‌کند."""
        cleaned = super().clean()
        if self.errors:
            return cleaned

        shop = self._current_shop
        text = cleaned.get("text_color") or (safe_hex(shop.text_color, "#241C3A") if shop else "#241C3A")
        background = cleaned.get("background_color") or (safe_hex(shop.background_color, "#F7F5FC") if shop else "#F7F5FC")
        surface = cleaned.get("surface_color") or (safe_hex(shop.surface_color, "#FFFFFF") if shop else "#FFFFFF")
        muted = cleaned.get("muted_text_color") or (safe_hex(shop.muted_text_color, "#8B86A3") if shop else "#8B86A3")

        failures = []
        if contrast_ratio(text, background) < 4.5:
            failures.append("رنگ متن اصلی در برابر پس‌زمینه‌ی صفحه خوانا نیست (کنتراست کمتر از ۴.۵)")
        if contrast_ratio(text, surface) < 4.5:
            failures.append("رنگ متن اصلی در برابر پس‌زمینه‌ی کارت‌ها خوانا نیست (کنتراست کمتر از ۴.۵)")
        if contrast_ratio(muted, surface) < 3.0:
            failures.append("رنگ متن کم‌رنگ در برابر پس‌زمینه‌ی کارت‌ها خوانا نیست (کنتراست کمتر از ۳)")

        if failures:
            raise forms.ValidationError(failures)
        return cleaned
