"""Backward-compat re-export — کد اصلی به ``apps.core.services.rate_limit``
منتقل شد (مصرف‌کننده‌ای مثلِ ``apps.sms`` نباید به ``apps.portal`` وابسته
شود). این ماژول را دست‌نخورده نگه می‌داریم تا وارد‌کننده‌های موجود نشکنند."""

from apps.core.services.rate_limit import RateLimitExceeded, enforce_rate_limit

__all__ = ["RateLimitExceeded", "enforce_rate_limit"]
