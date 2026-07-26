from django.apps import AppConfig


class StoresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stores"
    verbose_name = "فروشگاه‌ها (پلتفرم)"

    def ready(self):
        from . import admin_permissions

        admin_permissions.install()
