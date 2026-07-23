"""سرویس پنل مدیریت برای بخش پیامک تنظیمات — ویرایش قالب‌ها، اتصال، و گزارش.

هیچ منطق ارسال/اعتبارسنجی‌ای اینجا تکرار نمی‌شود؛ همه چیز از apps.sms.services
فراخوانی می‌شود (طبق اصل «منطق در لایه‌ی سرویس»، نه در ویو یا اینجا دوباره).
"""

from apps.sms.events import EVENT_VARIABLES, SmsEvent
from apps.sms.models import SmsLog, SmsTemplate

LOG_STATUS_FILTERS = [("", "همه وضعیت‌ها")] + list(SmsLog.Status.choices)

LOG_STATUS_BADGE = {
    SmsLog.Status.SENT: "b-green",
    SmsLog.Status.PENDING: "b-amber",
    SmsLog.Status.FAILED: "b-red",
}


def templates_with_variables():
    """قالب‌ها را به‌ترتیب رویدادها برمی‌گرداند؛ هرکدام همراه با فهرست متغیرهای مجازش."""
    SmsTemplate.ensure_defaults()
    templates = {t.event_key: t for t in SmsTemplate.objects.all()}
    rows = []
    for event_key in SmsEvent.values:
        template = templates.get(event_key)
        if template is None:
            continue
        rows.append({"template": template, "variables": EVENT_VARIABLES.get(event_key, {})})
    return rows


def filtered_logs(*, status: str = ""):
    qs = SmsLog.objects.order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs
