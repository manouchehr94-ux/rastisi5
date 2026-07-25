import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .hostnames import normalize_hostname


class StoresTimestampedModel(models.Model):
    """Local created_at/updated_at base for the ``stores`` app.

    ``apps.core.models.TimeStampedModel`` is not reused here on purpose.
    Several existing apps (catalog, orders, customers, ...) import from
    ``apps.core``, and a later foundation PR (see
    ``docs/architecture/SAAS_MIGRATION_PLAN.md``, PR 4) is expected to add a
    ``store`` foreign key to ``apps.core.ShopSettings`` itself — i.e. `core`
    is expected to depend on `stores` in the future. If `stores` imported
    from `core` now, that would set up a circular dependency between the two
    apps as soon as PR 4 lands. Defining timestamps locally here keeps
    `stores` dependency-free of `core` and avoids that future cycle.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Store(StoresTimestampedModel):
    """A Store is the authoritative SaaS tenant and data-ownership boundary.

    Every future commerce record must be either platform-global by explicit
    design, or owned directly or indirectly by exactly one Store. ``Store``
    is a new, independent domain entity — it is not ``apps.catalog.Vendor``
    and does not replace it. See
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` (ADR-1) for why the two
    are kept separate.

    This model intentionally has no owner field: Store ownership is
    represented exclusively through an active ``StoreMembership`` with
    ``role=OWNER`` (ADR-2), no billing/subscription/theme/payment fields,
    and no domain fields (``StoreDomain`` is a separate model on purpose).
    """

    class Status(models.TextChoices):
        PROVISIONING = "provisioning", "در حال آماده‌سازی"
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "معلق"
        CLOSED = "closed", "بسته‌شده"

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="شناسه‌ی عمومی پایدار برای ارجاع خارجی (API، صورتحساب، پشتیبانی).",
    )
    name = models.CharField("نام فروشگاه", max_length=200)
    slug = models.SlugField(
        "اسلاگ",
        max_length=200,
        unique=True,
        allow_unicode=True,
        help_text="یکتای سراسری در کل پلتفرم — نه فقط در یک فروشگاه.",
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=Status.choices,
        default=Status.PROVISIONING,
        db_index=True,
    )

    class Meta:
        verbose_name = "فروشگاه"
        verbose_name_plural = "فروشگاه‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StoreDomain(StoresTimestampedModel):
    """A hostname bound to a Store.

    ``hostname`` always holds the normalized, canonical form produced by
    ``apps.stores.hostnames.normalize_hostname`` — never a raw URL. See
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` (ADR-4, ADR-5) for the
    normalization and verification-lifecycle decisions. This model does not
    implement DNS/HTTP verification networking or request-time host
    resolution — those are later, separate PRs.
    """

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "تأییدنشده"
        PENDING = "pending", "در انتظار تأیید"
        VERIFIED = "verified", "تأییدشده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        Store,
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="domains",
    )
    hostname = models.CharField(
        "نام میزبان",
        max_length=253,
        unique=True,
        help_text="نام میزبان نرمال‌شده (بدون پروتکل/مسیر/پورت).",
    )
    is_primary = models.BooleanField("دامنه‌ی اصلی", default=False)

    verification_status = models.CharField(
        "وضعیت تأیید",
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )
    verification_token = models.CharField(
        "توکن تأیید", max_length=64, blank=True, default=""
    )
    verification_requested_at = models.DateTimeField(
        "زمان درخواست تأیید", null=True, blank=True
    )
    verified_at = models.DateTimeField("زمان تأیید", null=True, blank=True)

    class Meta:
        verbose_name = "دامنه‌ی فروشگاه"
        verbose_name_plural = "دامنه‌های فروشگاه"
        ordering = ["store", "-is_primary", "hostname"]
        constraints = [
            models.UniqueConstraint(
                fields=["store"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_domain_per_store",
            ),
            models.UniqueConstraint(
                fields=["verification_token"],
                condition=~models.Q(verification_token=""),
                name="uniq_verification_token_when_set",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "is_primary"], name="idx_domain_store_primary"),
        ]

    def __str__(self):
        marker = " (اصلی)" if self.is_primary else ""
        return f"{self.hostname}{marker}"

    def clean(self):
        super().clean()
        errors = {}

        if self.hostname:
            try:
                self.hostname = normalize_hostname(self.hostname)
            except ValidationError as exc:
                errors["hostname"] = exc.messages

        if (
            self.verification_status == self.VerificationStatus.VERIFIED
            and self.verified_at is None
        ):
            errors["verified_at"] = "دامنه‌ی تأییدشده باید زمان تأیید داشته باشد."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.hostname:
            self.hostname = normalize_hostname(self.hostname)
        super().save(*args, **kwargs)


class StoreMembership(StoresTimestampedModel):
    """The authoritative link between a User and a Store, carrying a role.

    Store ownership is represented exclusively through an active
    ``StoreMembership`` row with ``role=OWNER`` — ``Store`` has no separate
    ``owner`` field (ADR-2). This model establishes the data shape and its
    core invariants only; invitation delivery, tokenized acceptance, owner
    transfer, authorization decorators, and dashboard integration are later,
    separate PRs.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "مالک"
        ADMINISTRATOR = "administrator", "مدیر"
        CATALOG_MANAGER = "catalog_manager", "مدیر کاتالوگ"
        ORDER_MANAGER = "order_manager", "مدیر سفارش‌ها"
        CONTENT_EDITOR = "content_editor", "ویرایشگر محتوا"
        ANALYST = "analyst", "تحلیلگر"

    class MembershipStatus(models.TextChoices):
        INVITED = "invited", "دعوت‌شده"
        ACTIVE = "active", "فعال"
        REVOKED = "revoked", "لغوشده"

    store = models.ForeignKey(
        Store,
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        on_delete=models.CASCADE,
        related_name="store_memberships",
    )
    role = models.CharField("نقش", max_length=20, choices=Role.choices)
    status = models.CharField(
        "وضعیت عضویت",
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.INVITED,
        db_index=True,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="دعوت‌کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="store_invitations_sent",
    )
    invited_at = models.DateTimeField("زمان دعوت", auto_now_add=True)
    accepted_at = models.DateTimeField("زمان پذیرش", null=True, blank=True)
    revoked_at = models.DateTimeField("زمان لغو", null=True, blank=True)

    class Meta:
        verbose_name = "عضویت در فروشگاه"
        verbose_name_plural = "عضویت‌های فروشگاه"
        ordering = ["store", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "user"], name="uniq_membership_per_store_user"
            ),
            models.UniqueConstraint(
                fields=["store"],
                condition=models.Q(role="owner", status="active"),
                name="uniq_active_owner_per_store",
            ),
            models.CheckConstraint(
                check=~models.Q(status="active") | models.Q(accepted_at__isnull=False),
                name="active_membership_requires_accepted_at",
            ),
            models.CheckConstraint(
                check=~models.Q(status="revoked") | models.Q(revoked_at__isnull=False),
                name="revoked_membership_requires_revoked_at",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.store} ({self.get_role_display()})"

    def clean(self):
        super().clean()
        errors = {}

        if self.status == self.MembershipStatus.ACTIVE and self.accepted_at is None:
            errors["accepted_at"] = "عضویت فعال باید زمان پذیرش داشته باشد."
        if self.status == self.MembershipStatus.REVOKED and self.revoked_at is None:
            errors["revoked_at"] = "عضویت لغوشده باید زمان لغو داشته باشد."

        if errors:
            raise ValidationError(errors)
