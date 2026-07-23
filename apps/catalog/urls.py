from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("home/best-products/", views.home_best_products, name="home-best-products"),
    path("products/", views.product_list, name="product-list"),
    path("products/<uslug:slug>/", views.product_detail, name="product-detail"),
    path("products/<uslug:slug>/review/", views.product_review_create, name="product-review-create"),
]
