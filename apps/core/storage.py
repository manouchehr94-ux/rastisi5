"""ذخیره‌سازیِ خصوصیِ فایل‌های خروجی/ورودی — نگاه کنید به ADR-52 در
``SAAS_DOMAIN_DECISIONS.md``.

``PrivateFileSystemStorage`` عمداً هیچ ``base_url``ای ندارد — تلاش برای
گرفتنِ ``.url`` یک فایل همیشه ``ValueError`` می‌دهد (رفتارِ پیش‌فرضِ
Django's ``FileSystemStorage`` وقتی ``base_url=None``). این یک محافظِ
دفاعیِ عمدی است: حتی اگر جایی از کد به‌اشتباه سعی کند لینکِ مستقیمِ یک
فایلِ صادرات/واردات را در یک تمپلیت رندر کند، بلافاصله با خطا متوقف
می‌شود به‌جای انتشارِ خاموشِ یک لینکِ عمومی. تنها راهِ مجازِ خواندنِ این
فایل‌ها، یک ویوِ ``staff_required`` + Store-scoped است که مستقیماً از
دیسک می‌خواند و به‌عنوانِ ``FileResponse`` استریم می‌کند.

این کلاس عمداً یک زیرکلاسِ نام‌دارِ ``deconstructible`` است، نه یک
``FileSystemStorage(location=...)`` ساده — ``location`` را همیشه در زمانِ
اجرا از ``settings.PRIVATE_MEDIA_ROOT`` می‌خواند و ``deconstruct()`` هیچ
آرگومانی (نه ``location``، نه هیچ‌چیزِ دیگر) سریالایز نمی‌کند. اگر به‌جایش
یک نمونه‌ی ساده‌ی ``FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT))``
استفاده می‌شد، ``makemigrations`` مسیرِ مطلقِ حل‌شده‌ی همان ماشین (مثلاً
``D:\\Projects\\...`` روی ویندوز یا ``/home/user/...`` روی لینوکس) را
مستقیماً در فایلِ مهاجرت منجمد می‌کرد — و در نتیجه، اجرای ``makemigrations``
روی هر ماشینِ دیگری (یا حتی همان ماشین با مسیرِ نصبِ متفاوت) یک تغییرِ
جعلی گزارش می‌داد. با این کلاس، ``deconstruct()`` همیشه
``apps.core.storage.PrivateFileSystemStorage()`` بدونِ آرگومان برمی‌گرداند،
پس مهاجرت‌ها مستقلِ از مسیرِ نصب‌اند."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateFileSystemStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", str(settings.PRIVATE_MEDIA_ROOT))
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        return ("apps.core.storage.PrivateFileSystemStorage", [], {})


private_storage = PrivateFileSystemStorage()
