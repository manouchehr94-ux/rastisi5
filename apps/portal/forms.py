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


class ContactForm(forms.Form):
    full_name = forms.CharField(label="نام", max_length=150)
    email = forms.EmailField(label="ایمیل")
    subject = forms.CharField(label="موضوع", max_length=200, required=False)
    message = forms.CharField(label="پیام", widget=forms.Textarea, max_length=4000)
