"""تولید ``Store.platform_code`` — شناسه‌ی ۹ نویسه‌ای پایدار (ADR-94).

از الفبای ``settings.RASTISI_PLATFORM_CODE_ALPHABET`` (بدون 0/o/1/l/i برای
جلوگیری از ابهام بصری) با retry امن در برابر برخورد استفاده می‌کند. این
ماژول فقط تولید می‌کند — تخصیص به یک Store مشخص و ساخت ``StoreDomain``ی
که از این کد استفاده می‌کند بر عهده‌ی ``apps.portal.services.provisioning_
service`` است.
"""

import secrets

from django.conf import settings

from apps.stores.models import Store

_MAX_ATTEMPTS = 50


class PlatformCodeGenerationError(Exception):
    """پس از تلاش‌های مکرر، کد یکتای آزادی پیدا نشد (عملاً هرگز رخ نمی‌دهد)."""


def generate_unique_platform_code() -> str:
    alphabet = settings.RASTISI_PLATFORM_CODE_ALPHABET
    length = settings.RASTISI_PLATFORM_CODE_LENGTH
    for _attempt in range(_MAX_ATTEMPTS):
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if not Store.objects.filter(platform_code=candidate).exists():
            return candidate
    raise PlatformCodeGenerationError(
        f"could not generate a unique platform_code after {_MAX_ATTEMPTS} attempts"
    )
