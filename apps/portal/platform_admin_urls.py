from django.urls import path

from . import platform_admin_views as views

app_name = "portal_platform_admin"

urlpatterns = [
    path("", views.home, name="home"),
    path("configuration/", views.configuration, name="configuration"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
