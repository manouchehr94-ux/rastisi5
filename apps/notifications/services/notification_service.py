"""صف/تحویلِ اعلان‌ها (Section 16). ``enqueue`` هرگز چیزی ارسال نمی‌کند —
فقط یک ردیفِ پایدار می‌سازد؛ ``deliver_pending`` تنها جایی است که واقعاً
پیامک/ایمیل می‌فرستد (یا برایِ درون‌برنامه‌ای، صرفاً موجودیِ خودِ ردیف را
تحویل‌شده حساب می‌کند). یک خطای ارسال هرگز اعلان را از دست نمی‌دهد — فقط
``FAILED`` می‌شود و در اجرایِ بعدیِ ``deliver_pending`` دوباره تلاش
می‌شود."""

from django.utils import timezone

from apps.notifications.models import NotificationOutbox

C = NotificationOutbox.Channel
S = NotificationOutbox.Status


def enqueue(
    *, channel: str, body: str, subject: str = "", recipient_user=None, recipient_phone: str = "",
    recipient_email: str = "", store=None, is_security: bool = False, metadata: dict | None = None,
) -> NotificationOutbox:
    return NotificationOutbox.objects.create(
        channel=channel, subject=subject, body=body, recipient_user=recipient_user,
        recipient_phone=recipient_phone, recipient_email=recipient_email, store=store,
        is_security=is_security, metadata=metadata or {},
    )


def _deliver_one(notification: NotificationOutbox) -> None:
    if notification.channel == C.IN_APP:
        return  # خودِ ردیف تحویل است — نیازی به ارسالِ خارجی نیست.

    if notification.channel == C.SMS:
        from apps.portal.services.owner_sms_service import send_platform_sms

        result = send_platform_sms(to=notification.recipient_phone, text=notification.body)
        if not result.success:
            raise RuntimeError(result.error_message or "ارسالِ پیامک ناموفق بود")
        return

    if notification.channel == C.EMAIL:
        from django.conf import settings
        from django.core.mail import send_mail

        send_mail(
            notification.subject, notification.body, settings.DEFAULT_FROM_EMAIL,
            [notification.recipient_email], fail_silently=False,
        )
        return

    raise RuntimeError(f"کانالِ ناشناخته: {notification.channel}")


def deliver_pending(*, limit: int = 200) -> dict:
    pending = NotificationOutbox.objects.filter(status=S.PENDING).order_by("created_at")[:limit]
    sent = 0
    failed = 0
    for notification in pending:
        notification.attempts += 1
        try:
            _deliver_one(notification)
        except Exception as exc:  # noqa: BLE001 — یک اعلانِ خراب نباید بقیه‌ی صف را متوقف کند
            notification.status = S.FAILED
            notification.last_error = str(exc)
            failed += 1
        else:
            notification.status = S.SENT
            notification.sent_at = timezone.now()
            notification.last_error = ""
            sent += 1
        notification.save(update_fields=["status", "attempts", "sent_at", "last_error", "updated_at"])
    return {"processed": sent + failed, "sent": sent, "failed": failed}


def notify_security_event(
    *, subject: str, body: str, user=None, phone: str = "", store=None, metadata: dict | None = None,
) -> list[NotificationOutbox]:
    """اعلانِ امنیتی — بدونِ هیچ مسیرِ opt-out. اگر ``user`` داده شود یک
    اعلانِ درون‌برنامه‌ای، و اگر ``phone`` داده شود یک پیامک، صف می‌شود."""
    created = []
    if user is not None:
        created.append(enqueue(
            channel=C.IN_APP, subject=subject, body=body, recipient_user=user,
            store=store, is_security=True, metadata=metadata,
        ))
    if phone:
        created.append(enqueue(
            channel=C.SMS, body=body, recipient_phone=phone, store=store, is_security=True, metadata=metadata,
        ))
    return created
