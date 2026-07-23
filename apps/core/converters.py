class UnicodeSlugConverter:
    """مشابه مبدل داخلی Django's slug ولی برای اسلاگ‌های یونیکد (allow_unicode=True) هم کار می‌کند.

    مبدل داخلی `<slug:...>` فقط ASCII را می‌پذیرد؛ چون همه‌ی SlugField های
    این پروژه با allow_unicode=True ساخته می‌شوند، اسلاگ فارسی باید در
    URL هم قابل تطبیق باشد.
    """

    regex = r"[-\w]+"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
