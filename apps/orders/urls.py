from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.checkout_step1, name="checkout-step1"),
    path("address/", views.checkout_address_save, name="checkout-address-save"),
    path("items/<int:item_id>/update/", views.checkout_item_update, name="checkout-item-update"),
    path("items/<int:item_id>/remove/", views.checkout_item_remove, name="checkout-item-remove"),
    path("shipping/<int:method_id>/", views.checkout_set_shipping, name="checkout-set-shipping"),
    path("payment/<int:gateway_id>/", views.checkout_set_payment, name="checkout-set-payment"),
    path("coupon/apply/", views.checkout_apply_coupon, name="checkout-coupon-apply"),
    path("coupon/remove/", views.checkout_remove_coupon, name="checkout-coupon-remove"),
]
