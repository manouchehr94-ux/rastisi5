from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("home/best-products/", views.home_best_products, name="home-best-products"),
]
