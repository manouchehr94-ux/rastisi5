import re

from django import forms

from apps.core.utils import normalize_digits

PHONE_RE = re.compile(r"^09\d{9}$")
POSTAL_RE = re.compile(r"^\d{10}$")


class PhoneCleanMixin:
    def clean_phone(self):
        phone = normalize_digits(self.cleaned_data["phone"]).strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("شماره موبایل معتبر نیست (مثال: 09123456789)")
        return phone


class LoginForm(PhoneCleanMixin, forms.Form):
    phone = forms.CharField(label="شماره موبایل", max_length=15)
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class SignupForm(PhoneCleanMixin, forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    phone = forms.CharField(label="شماره موبایل", max_length=15)
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class ProfileForm(forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل", required=False)
    city = forms.CharField(label="شهر", max_length=80, required=False)


class AddressForm(PhoneCleanMixin, forms.Form):
    receiver_name = forms.CharField(label="نام گیرنده", max_length=150)
    phone = forms.CharField(label="شماره موبایل گیرنده", max_length=15)
    province = forms.CharField(label="استان", max_length=80)
    city = forms.CharField(label="شهر", max_length=80)
    postal_code = forms.CharField(label="کد پستی", max_length=10, required=False)
    full_address = forms.CharField(label="آدرس پستی کامل", widget=forms.Textarea)

    def clean_postal_code(self):
        postal_code = normalize_digits(self.cleaned_data.get("postal_code", "")).strip()
        if postal_code and not POSTAL_RE.match(postal_code):
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد")
        return postal_code
