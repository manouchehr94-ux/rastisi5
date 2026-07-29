"""ذخیره‌سازیِ خصوصیِ فایل‌های خروجی/ورودی — نگاه کنید به ADR-52 در
``SAAS_DOMAIN_DECISIONS.md``.

``PrivateFileSystemStorage`` عمداً هیچ ``base_url``ای ندارد — تلاش برای
گرفتنِ ``.url`` یک فایل همیشه ``ValueError`` می‌دهد (رفتارِ پیش‌فرضِ
Django's ``FileSystemStorage`` وقتی ``base_url=None``). این یک محافظِ
دفاعیِ عمدی است: حتی اگر جایی از کد به‌اشتباه سعی کند لینکِ مستقیمِ یک
فایلِ صادرات/واردات را در یک تمپلیت رندر کند، بلافاصله با خطا متوقف
می‌شود به‌جای انتشارِ خاموشِ یک لینکِ عمومی. تنها راهِ مجازِ خواندنِ این
فایل‌ها، یک ویوِ ``staff_required`` + Store-scoped است که مستقیماً از
دیسک می‌خواند و به‌عنوانِ ``FileResponse`` استریم می‌کند."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage

private_storage = FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)
