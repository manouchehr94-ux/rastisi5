from decimal import Decimal, InvalidOperation

from django import forms

from apps.catalog.models import Category, Product
from apps.core.utils import normalize_digits

from .services.catalog_admin_service import leaf_categories


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

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.fields["category"].queryset = leaf_categories()

    def clean_sku(self):
        sku = normalize_digits(self.cleaned_data["sku"]).strip()
        if not sku:
            raise forms.ValidationError("کد کالا الزامی است")
        qs = Product.objects.filter(sku=sku)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این کد کالا قبلاً استفاده شده است")
        return sku

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


class MainCategoryForm(forms.Form):
    name = forms.CharField(label="نام گروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False, initial="📁")


class SubCategoryForm(forms.Form):
    parent = forms.ModelChoiceField(
        label="گروه والد", queryset=Category.objects.filter(parent__isnull=True).order_by("order", "name"),
        error_messages={"required": "انتخاب گروه والد الزامی است"},
    )
    name = forms.CharField(label="نام زیرگروه", max_length=120)
    icon = forms.CharField(label="آیکون (ایموجی)", max_length=10, required=False)


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
