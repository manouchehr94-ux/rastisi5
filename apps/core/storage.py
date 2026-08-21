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
from django.core.files.storage import FileSystemStorage, storages
from django.utils.deconstruct import deconstructible
from django.utils.functional import LazyObject


@deconstructible
class PrivateFileSystemStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", str(settings.PRIVATE_MEDIA_ROOT))
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        return ("apps.core.storage.PrivateFileSystemStorage", [], {})


class _PrivateStorageProxy(LazyObject):
    """پراکسیِ پایدار برایِ بک‌اندِ فعلیِ alias «private» در ``STORAGES``.

    عمداً با ``@deconstructible`` تزئین نشده — آن دکوریتور یک ``__new__``
    اضافه می‌کند که تلاش می‌کند ``_constructor_args`` را روی خودِ نمونه
    ست کند، اما ``LazyObject.__setattr__`` هر ست‌کردنِ attributeی غیر از
    ``_wrapped`` را به شیءِ داخلیِ هنوز مقداردهی‌نشده (``_wrapped`` هنوز
    ``None``/``empty`` است، چون ``__init__`` هنوز اجرا نشده) هدایت
    می‌کند — که بلافاصله ``AttributeError`` می‌دهد. چون این کلاس خودش
    ``deconstruct()`` را کامل override می‌کند، به رفتارِ خودکارِ
    ``@deconstructible`` نیازی نیست؛ سریالایزرِ مهاجراتِ جنگو فقط به
    وجودِ متدِ ``deconstruct()`` نیاز دارد، نه به خودِ دکوریتور.

    ``ExportJob``/``ImportJob`` (apps/core/models.py) این شیء را مستقیماً
    به‌عنوانِ ``storage=`` به FileField می‌دهند — یعنی (برخلافِ الگویِ
    ``default_storage`` خودِ Django که ``FileField.deconstruct()`` با
    مقایسه‌ی identity ویژه‌اش می‌کند و اصلاً در مهاجرت ثبت نمی‌شود) این مقدار
    همیشه در ``deconstruct()``ی خودِ فیلد سریالایز می‌شود — دقیقاً همان
    چیزی که مهاجرتِ تاریخیِ
    core/migrations/0014_private_storage_deconstructible.py با
    ``apps.core.storage.PrivateFileSystemStorage()`` منجمد کرده.

    اگر این شیء را مستقیماً با نمونه‌ی واقعیِ resolve‌شده (``storages["private"]``)
    جایگزین می‌کردیم، به‌محضِ این‌که یک استقرارِ آینده
    ``STORAGES["private"]["BACKEND"]`` را به بک‌اندِ دیگری تغییر دهد،
    ``deconstruct()``یِ آن بک‌اندِ *متفاوت* وارد state مدل می‌شد — و
    ``makemigrations --check`` نسبت به همین مهاجرتِ ۰۰۱۴ یک AlterField
    جعلی گزارش می‌داد، دقیقاً برخلافِ ادعای «تعویضِ بک‌اند فقط پیکربندی
    است، نه مهاجرت».

    این کلاس آن مشکل را با همان الگویِ خودِ Django حل می‌کند
    (``django.core.files.storage.DefaultStorage``، یک ``LazyObject`` که
    ``storages["default"]`` را lazily resolve می‌کند): ``deconstruct()``
    همیشه همان تاپلِ ثابتِ بالا را برمی‌گرداند — مستقل از این‌که
    ``_setup()`` واقعاً چه بک‌اندی را resolve کرده — درحالی‌که هر عملیاتِ
    واقعیِ فایل (``save``/``open``/``exists``/``delete``/``path``/``url``)
    از طریقِ مکانیزمِ پراکسیِ خودِ ``LazyObject`` (``__getattr__``) به
    همان بک‌اندِ واقعاً پیکربندی‌شده هدایت می‌شود. نتیجه: تعویضِ بک‌اند
    واقعاً فقط پیکربندی می‌ماند، برایِ همیشه — نه فقط تا وقتی بک‌اندِ
    جدید هم به‌طورِ اتفاقی همان‌طور deconstruct شود."""

    def _setup(self):
        self._wrapped = storages["private"]

    def deconstruct(self):
        return ("apps.core.storage.PrivateFileSystemStorage", [], {})


# نگاه کنید به _PrivateStorageProxy بالا — deconstruct() این شیء همیشه
# پایدار می‌ماند؛ resolve واقعیِ بک‌اند (از طریقِ STORAGES["private"]،
# shop_core/settings.py) تنبل و مستقل از این ثباتِ مهاجرتی است.
private_storage = _PrivateStorageProxy()
