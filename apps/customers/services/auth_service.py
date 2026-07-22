"""لایه‌ی سرویس احراز هویت — ثبت‌نام، ورود (موبایل + رمز) و ادغام سبد مهمان.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۵. شناسه‌ی ورود شماره موبایل
است (آماده برای جایگزینی رمز با کد یکبارمصرف در فازهای بعد)؛ نام کاربری داخلی
جنگو برای کاربران جدید همان شماره موبایل است، اما به آن گره نخورده‌ایم — ورود
همیشه از روی Customer.phone انجام می‌شود تا با کاربران seed (با نام کاربری
دلخواه) هم سازگار باشد.

ادغام «علاقه‌مندی‌ها»ی مهمان معنا ندارد چون Wishlist (مرحله‌ی ۱) از ابتدا فقط
برای کاربر واردشده تعریف شده و session_key ندارد؛ مهمان اصلاً نمی‌تواند پیش از
ورود چیزی به علاقه‌مندی اضافه کند.
"""

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.cart.models import Cart
from apps.customers.models import Customer

User = get_user_model()


class AuthError(Exception):
    """خطای قابل‌نمایش به کاربر در فرم ورود/ثبت‌نام."""


@transaction.atomic
def signup(*, full_name: str, phone: str, password: str) -> Customer:
    if Customer.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
        raise AuthError("این شماره موبایل قبلاً ثبت‌نام کرده است")
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise AuthError(" ".join(exc.messages)) from exc

    user = User.objects.create_user(username=phone, password=password)
    return Customer.objects.create(user=user, full_name=full_name, phone=phone)


def authenticate_customer(request, *, phone: str, password: str):
    """با موبایل و رمز احراز هویت می‌کند و در صورت موفقیت User را برمی‌گرداند، وگرنه None."""
    customer = Customer.objects.select_related("user").filter(phone=phone).first()
    if customer is None:
        return None
    return authenticate(request, username=customer.user.username, password=password)


@transaction.atomic
def merge_guest_cart(request, customer: Customer) -> None:
    """سبد خرید مهمان (بر اساس session_key) را با سبد کاربر واردشده ادغام می‌کند."""
    session_key = request.session.session_key
    if not session_key:
        return
    guest_cart = Cart.objects.filter(session_key=session_key, customer__isnull=True).first()
    if guest_cart is None:
        return

    user_cart, _ = Cart.objects.get_or_create(customer=customer)
    for item in guest_cart.items.select_related("product", "variant"):
        existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
        if existing:
            existing.quantity += item.quantity
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            item.cart = user_cart
            item.save(update_fields=["cart", "updated_at"])
    guest_cart.delete()
