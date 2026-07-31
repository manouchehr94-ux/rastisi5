"""لایه‌ی سرویسِ هویتِ مالک — ثبت‌نام/ورود/بازیابیِ رمز با ایمیل+رمز عبور.

عمداً از ``apps.customers.services.auth_service`` جداست (ADR-93): آن سرویس
مشتریِ فروشگاه می‌سازد (شناسه = موبایل، همیشه به یک ``store`` وابسته است)؛
این‌جا مالکِ پلتفرم ساخته می‌شود (شناسه = ایمیل، مستقل از هر Store‌ای —
مالک قبل از ساختِ اولین Store هم باید بتواند ثبت‌نام کند).
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.portal.models import OwnerProfile

User = get_user_model()


class OwnerAuthError(Exception):
    """خطای قابل‌نمایش به کاربر در فرم ثبت‌نام/ورود/بازیابیِ رمزِ پرتال."""


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


@transaction.atomic
def register_owner(*, full_name: str, email: str, password: str) -> User:
    email = _normalize_email(email)
    if not email:
        raise OwnerAuthError("ایمیل الزامی است")
    if User.objects.filter(email__iexact=email).exists():
        raise OwnerAuthError("این ایمیل قبلاً ثبت‌نام کرده است")
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise OwnerAuthError(" ".join(exc.messages)) from exc

    user = User.objects.create_user(username=email, email=email, password=password)
    OwnerProfile.objects.create(user=user, full_name=full_name.strip())
    return user


def authenticate_owner(request, *, email: str, password: str):
    """با ایمیل و رمز احراز هویت می‌کند و در صورت موفقیت User را برمی‌گرداند، وگرنه None."""
    return authenticate(request, username=_normalize_email(email), password=password)


def request_password_reset(*, email: str, base_url: str) -> None:
    """اگر ایمیل متعلق به کاربری باشد ایمیل بازیابی می‌فرستد؛ در غیر این صورت
    بی‌صدا کاری نمی‌کند — تا فرمِ عمومی هرگز فاش نکند کدام ایمیل ثبت‌نام کرده
    (enumeration-safety). ``base_url`` مثلِ ``"https://rastisi.ir"`` — بدونِ
    اسلش پایانی."""
    user = User.objects.filter(email__iexact=_normalize_email(email)).first()
    if user is None:
        return
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f"{base_url}/reset-password/{uidb64}/{token}/"
    body = render_to_string(
        "portal/public/emails/password_reset.txt",
        {"user": user, "reset_url": reset_url},
    )
    send_mail(
        subject="بازیابی رمز عبور راستیسی",
        message=body,
        from_email=None,
        recipient_list=[user.email],
        fail_silently=True,
    )


def get_user_from_reset_link(*, uidb64: str, token: str):
    """کاربر را از uid رمزگشایی‌شده برمی‌گرداند اگر توکن معتبر باشد، وگرنه None."""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user


@transaction.atomic
def set_new_password(*, user, password: str) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise OwnerAuthError(" ".join(exc.messages)) from exc
    user.set_password(password)
    user.save(update_fields=["password"])
