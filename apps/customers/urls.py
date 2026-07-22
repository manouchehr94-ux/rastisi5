from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("wishlist/", views.wishlist_list, name="wishlist"),
    path("wishlist/<slug:slug>/toggle/", views.wishlist_toggle, name="wishlist-toggle"),
]
