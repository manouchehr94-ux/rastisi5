from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.admin_login, name="login"),
    path("", views.dashboard_home, name="dashboard"),
    path("sales-chart/", views.sales_chart_partial, name="sales-chart"),

    path("products/", views.product_list, name="product-list"),
    path("products/table/", views.product_table, name="product-table"),
    path("products/add/", views.product_form, name="product-add"),
    path("products/<int:pk>/edit/", views.product_form, name="product-edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product-delete"),

    path("products/<int:pk>/images/", views.product_images, name="product-images"),
    path("products/<int:pk>/images/upload/", views.product_image_upload, name="product-image-upload"),
    path("products/<int:pk>/images/<int:image_id>/delete/", views.product_image_delete, name="product-image-delete"),
    path("products/<int:pk>/images/<int:image_id>/cover/", views.product_image_set_cover, name="product-image-set-cover"),
    path("products/<int:pk>/images/<int:image_id>/move/", views.product_image_move, name="product-image-move"),
    path("products/<int:pk>/images/<int:image_id>/alt/", views.product_image_alt_update, name="product-image-alt"),

    path("categories/", views.category_list, name="category-list"),
    path("categories/add-main/", views.category_add_main, name="category-add-main"),
    path("categories/add-sub/", views.category_add_sub, name="category-add-sub"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category-edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category-delete"),

    path("orders/", views.order_list, name="order-list"),
    path("orders/table/", views.order_table, name="order-table"),
    path("orders/<str:code>/", views.order_detail, name="order-detail"),

    path("invoices/", views.invoice_list, name="invoice-list"),
    path("invoices/table/", views.invoice_table, name="invoice-table"),
    path("invoices/<str:code>/", views.invoice_detail, name="invoice-detail"),

    path("payments/", views.payment_list, name="payment-list"),
    path("payments/table/", views.payment_table, name="payment-table"),

    path("customers/", views.customer_list, name="customer-list"),
    path("customers/table/", views.customer_table, name="customer-table"),
    path("customers/<int:pk>/", views.customer_detail, name="customer-detail"),

    path("reports/", views.report_list, name="report-list"),
    path("reports/body/", views.report_partial, name="report-body"),

    path("settings/", views.settings_home, name="settings"),
    path("settings/shop-info/", views.settings_shop_info, name="settings-shop-info"),
    path("settings/finance/", views.settings_finance, name="settings-finance"),
    path("settings/appearance/", views.settings_appearance, name="settings-appearance"),
    path("settings/gateways/<int:pk>/toggle/", views.settings_gateway_toggle, name="settings-gateway-toggle"),
    path("settings/shipping/<int:pk>/toggle/", views.settings_shipping_toggle, name="settings-shipping-toggle"),

    path("settings/sms/connection/", views.settings_sms_connection, name="settings-sms-connection"),
    path("settings/sms/templates/<int:pk>/edit/", views.sms_template_form, name="sms-template-edit"),
    path("settings/sms/templates/<int:pk>/toggle/", views.sms_template_toggle, name="sms-template-toggle"),
    path("settings/sms/test-send/", views.sms_test_send, name="sms-test-send"),
    path("settings/sms/logs/", views.sms_log_list, name="sms-log-list"),
    path("settings/sms/logs/table/", views.sms_log_table, name="sms-log-table"),

    # --- صفحات محتوایی ---
    path("pages/", views.page_list, name="page-list"),
    path("pages/add/", views.page_form, name="page-add"),
    path("pages/<int:pk>/edit/", views.page_form, name="page-edit"),
    path("pages/<int:pk>/delete/", views.page_delete, name="page-delete"),
    path("pages/<int:pk>/publish/", views.page_publish, name="page-publish"),

    # --- صفحه اصلی ---
    path("homepage/hero/", views.hero_list, name="hero-list"),
    path("homepage/hero/add/", views.hero_form, name="hero-add"),
    path("homepage/hero/<int:pk>/edit/", views.hero_form, name="hero-edit"),
    path("homepage/hero/<int:pk>/delete/", views.hero_delete, name="hero-delete"),
    path("homepage/hero/<int:pk>/toggle/", views.hero_toggle, name="hero-toggle"),
    path("homepage/banners/", views.banner_list, name="banner-list"),
    path("homepage/banners/add/", views.banner_form, name="banner-add"),
    path("homepage/banners/<int:pk>/edit/", views.banner_form, name="banner-edit"),
    path("homepage/banners/<int:pk>/delete/", views.banner_delete, name="banner-delete"),
    path("homepage/banners/<int:pk>/toggle/", views.banner_toggle, name="banner-toggle"),
]
