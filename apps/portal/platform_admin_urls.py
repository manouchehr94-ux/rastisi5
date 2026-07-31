from django.urls import path

from . import platform_admin_views as views

app_name = "portal_platform_admin"

urlpatterns = [
    path("", views.home, name="home"),
    path("stores/", views.stores, name="stores"),
    path("stores/<uuid:store_public_id>/", views.store_detail, name="store-detail"),
    path("audit-log/", views.audit_log, name="audit-log"),
    path("configuration/", views.configuration, name="configuration"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
