from django import forms


class OwnerRegisterForm(forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل")
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class OwnerLoginForm(forms.Form):
    email = forms.EmailField(label="ایمیل")
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="ایمیل")


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(label="رمز عبور جدید", widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="تکرار رمز عبور", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password_confirm"):
            raise forms.ValidationError("رمز عبور و تکرار آن یکسان نیستند")
        return cleaned


class CreateStoreForm(forms.Form):
    name = forms.CharField(label="نام فروشگاه", max_length=200)
    industry_template_id = forms.IntegerField(label="صنف", required=False)
    submission_token = forms.CharField(widget=forms.HiddenInput, required=False)


class PlatformConfigurationForm(forms.ModelForm):
    class Meta:
        from .models import PlatformConfiguration

        model = PlatformConfiguration
        fields = [
            "default_trial_days", "deletion_retention_days",
            "primary_brand_color", "secondary_brand_color",
            "temporary_logo_text", "logo",
            "support_contact_phone", "support_contact_email",
            "default_payment_provider",
        ]

    def clean_deletion_retention_days(self):
        days = self.cleaned_data["deletion_retention_days"]
        if not (180 <= days <= 365):
            raise forms.ValidationError("روزهای نگهداری باید بین ۱۸۰ تا ۳۶۵ باشد.")
        return days


class ContactForm(forms.Form):
    full_name = forms.CharField(label="نام", max_length=150)
    email = forms.EmailField(label="ایمیل")
    subject = forms.CharField(label="موضوع", max_length=200, required=False)
    message = forms.CharField(label="پیام", widget=forms.Textarea, max_length=4000)
