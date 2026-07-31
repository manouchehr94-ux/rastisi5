from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


def owner_required(view_func):
    """معادلِ ``login_required`` جنگو، اما مخصوصِ پرتالِ مالکان — به صفحه‌ی
    ورودِ اختصاصیِ پرتال (``portal:login``) هدایت می‌کند، نه ``settings.
    LOGIN_URL`` سراسری (که اینجا دست‌نخورده می‌ماند تا هیچ مسیرِ ورودِ دیگری
    در پروژه، مثلِ ویوهای مشتری، تحتِ تأثیر قرار نگیرد)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            params = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('portal:login')}?{params}")
        return view_func(request, *args, **kwargs)

    return wrapper
