from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        from django.urls import register_converter

        from . import checks  # noqa: F401 — import registers the @register()'d checks
        from .converters import UnicodeSlugConverter

        register_converter(UnicodeSlugConverter, "uslug")
