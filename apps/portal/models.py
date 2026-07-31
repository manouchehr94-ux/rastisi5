import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class OwnerProfile(TimeStampedModel):
    """Portal-only profile data for a Store-owner ``User``.

    Deliberately separate from ``apps.customers.models.Customer`` (ADR-93):
    an owner registering through the portal never gets a ``Customer`` row as
    a side effect, and a storefront customer never gets an ``OwnerProfile``.
    Both are optional one-to-one extensions of the same plain ``auth.User``
    table — a person can hold either, both, or neither.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="owner_profile",
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)

    class Meta:
        verbose_name = "پروفایل مالک"
        verbose_name_plural = "پروفایل‌های مالک"

    def __str__(self):
        return self.full_name or self.user.email


def _generate_handoff_token() -> str:
    return secrets.token_urlsafe(32)


class AdminHandoffTicket(TimeStampedModel):
    """Single-use, short-lived ticket bridging owner-portal auth to a Store's
    distinct Merchant Admin host (ADR-98).

    ``SESSION_COOKIE_DOMAIN`` is unset in this project (host-only cookies by
    design), so a logged-in owner on the portal host has no session on
    ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}``. This ticket is
    issued only for a (user, store) pair with an active ``StoreMembership``,
    is valid for a short window, and is consumed exactly once (atomically) by
    the admin-host handoff view, which then calls Django's own ``login()``
    for that host. It grants no authorization by itself — every subsequent
    admin-portal request still goes through the existing ``staff_required``/
    membership checks unchanged.
    """

    token = models.CharField("توکن", max_length=64, unique=True, default=_generate_handoff_token, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    destination_path = models.CharField("مسیر مقصد", max_length=200, default="/admin-portal/")
    expires_at = models.DateTimeField("زمان انقضا")
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)

    class Meta:
        verbose_name = "بلیت ورود به پنل مدیریت"
        verbose_name_plural = "بلیت‌های ورود به پنل مدیریت"
        indexes = [
            models.Index(fields=["token", "consumed_at"], name="idx_handoff_token_consumed"),
        ]

    def __str__(self):
        return f"handoff:{self.user_id}->{self.store_id}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired


class ContactMessage(TimeStampedModel):
    """پیامِ ثبت‌شده از فرم «تماس با ما»ی سایت عمومی راستیسی.

    فقط ذخیره می‌کند — بدون صف/ارسال پیامک/ایمیل خودکار. بازبینیِ این پیام‌ها
    بخشی از پنل مدیریت پلتفرم (Section M) است."""

    full_name = models.CharField("نام", max_length=150)
    email = models.EmailField("ایمیل")
    subject = models.CharField("موضوع", max_length=200, blank=True, default="")
    message = models.TextField("پیام")
    is_reviewed = models.BooleanField("بررسی‌شده", default=False)

    class Meta:
        verbose_name = "پیام تماس"
        verbose_name_plural = "پیام‌های تماس"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"
