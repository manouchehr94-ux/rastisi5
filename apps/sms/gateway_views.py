"""Endpointِ عمومیِ poll/ack برایِ گیت‌وی اندرویدِ SmsRasti.

بدونِ CSRF (کلاینت یک اپ اندرویدِ خارجی است، نه مرورگر) و بدونِ نیاز به
resolve شدنِ Store از رویِ Host — احرازِ هویت فقط با device_token است
(``ShopSettings.smsrasti_device_token``، منحصربه‌فرد در کلِ پلتفرم)، پس
تمامِ query ها ذاتاً به همان Store محدود می‌مانند، نه با اعتمادِ بر پارامتر
ورودیِ store/tenant.

چرخه‌ی عمر عمداً دو مرحله‌ای است — poll فقط ``sending`` می‌کند، ack صریح
است که ``sent``/``failed`` می‌کند — دقیقاً برایِ جلوگیری از باگِ نسخه‌ی
مرجع که صرفِ poll شدن را «ارسال‌شده» علامت می‌زد."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import ShopSettings

from .models import SmsOutboxItem

# اگر گیت‌وی یک پیام را claim کند اما هرگز ack نفرستد (کرش، قطعیِ شبکه)،
# پس از این مدت دوباره قابلِ claim‌شدن است — تا برایِ همیشه گیر نکند.
RECLAIM_AFTER_SECONDS = 120


def _device_shop(request):
    token = request.GET.get("token") or request.POST.get("token") or ""
    if not token:
        return None
    return ShopSettings.objects.filter(smsrasti_device_token=token).first()


@csrf_exempt
@require_GET
def smsrasti_poll(request):
    shop = _device_shop(request)
    if shop is None:
        return JsonResponse({"status": "error", "message": "unauthorized"}, status=401)

    stale_cutoff = timezone.now() - timedelta(seconds=RECLAIM_AFTER_SECONDS)
    with transaction.atomic():
        item = (
            SmsOutboxItem.objects
            .select_for_update(skip_locked=True)
            .filter(store=shop.store)
            .filter(
                Q(status=SmsOutboxItem.Status.PENDING)
                | Q(status=SmsOutboxItem.Status.SENDING, claimed_at__lt=stale_cutoff)
            )
            .order_by("created_at")
            .first()
        )
        if item is None:
            return JsonResponse({"status": "empty"})

        item.status = SmsOutboxItem.Status.SENDING
        item.claimed_at = timezone.now()
        item.attempt_count += 1
        item.save(update_fields=["status", "claimed_at", "attempt_count", "updated_at"])

    return JsonResponse(
        {"status": "ok", "id": item.pk, "phone": item.phone, "message": item.message},
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_POST
def smsrasti_ack(request):
    shop = _device_shop(request)
    if shop is None:
        return JsonResponse({"status": "error", "message": "unauthorized"}, status=401)

    outcome = request.POST.get("status") or "sent"
    error = request.POST.get("error") or ""
    ref_id = request.POST.get("rec_id") or ""

    try:
        item = SmsOutboxItem.objects.get(pk=request.POST.get("id"), store=shop.store)
    except (SmsOutboxItem.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"status": "error", "message": "not found"}, status=404)

    if outcome == "sent":
        item.status = SmsOutboxItem.Status.SENT
        item.sent_at = timezone.now()
        item.provider_ref_id = ref_id
        item.error_message = ""
    else:
        item.status = SmsOutboxItem.Status.FAILED
        item.error_message = error or "گیت‌وی اندروید ارسال را ناموفق اعلام کرد"
    item.save(update_fields=["status", "sent_at", "provider_ref_id", "error_message", "updated_at"])
    return JsonResponse({"status": "ok"})
