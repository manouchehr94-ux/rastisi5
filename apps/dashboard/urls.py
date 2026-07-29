from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.admin_login, name="login"),
    path("", views.dashboard_home, name="dashboard"),
    path("sales-chart/", views.sales_chart_partial, name="sales-chart"),

    path("products/", views.product_list, name="product-list"),
    path("products/table/", views.product_table, name="product-table"),
    path("products/bulk-action/", views.product_bulk_action, name="product-bulk-action"),
    path("products/add/", views.product_form, name="product-add"),
    path("products/<int:pk>/edit/", views.product_form, name="product-edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product-delete"),
    path("products/attribute-fields/", views.product_attribute_fields, name="product-attribute-fields"),
    path("products/<int:pk>/attribute-fields/", views.product_attribute_fields, name="product-attribute-fields-edit"),
    path("products/<int:pk>/attribute-fields/cleanup/", views.product_attribute_cleanup_orphans, name="product-attribute-cleanup"),

    path("products/<int:pk>/images/", views.product_images, name="product-images"),
    path("products/<int:pk>/images/upload/", views.product_image_upload, name="product-image-upload"),
    path("products/<int:pk>/images/<int:image_id>/delete/", views.product_image_delete, name="product-image-delete"),
    path("products/<int:pk>/images/<int:image_id>/cover/", views.product_image_set_cover, name="product-image-set-cover"),
    path("products/<int:pk>/images/<int:image_id>/move/", views.product_image_move, name="product-image-move"),
    path("products/<int:pk>/images/<int:image_id>/alt/", views.product_image_alt_update, name="product-image-alt"),
    path("products/<int:pk>/images/<int:image_id>/variant/", views.product_image_variant_update, name="product-image-variant"),

    path("products/<int:pk>/variants/", views.product_variants, name="product-variants"),
    path("products/<int:pk>/variants/bulk-add/", views.product_variant_bulk_add, name="product-variant-bulk-add"),
    path("products/<int:pk>/variants/<int:variant_id>/edit/", views.product_variant_edit, name="product-variant-edit"),
    path("products/<int:pk>/variants/<int:variant_id>/toggle/", views.product_variant_toggle, name="product-variant-toggle"),
    path("products/<int:pk>/variants/<int:variant_id>/delete/", views.product_variant_delete, name="product-variant-delete"),
    path("products/<int:pk>/variants/<int:variant_id>/move/", views.product_variant_move, name="product-variant-move"),

    path("attributes/", views.attribute_list, name="attribute-list"),
    path("attributes/table/", views.attribute_table, name="attribute-table"),
    path("attributes/add/", views.attribute_add, name="attribute-add"),
    path("attributes/<int:pk>/edit/", views.attribute_edit, name="attribute-edit"),
    path("attributes/<int:pk>/archive/", views.attribute_archive, name="attribute-archive"),
    path("attributes/<int:pk>/activate/", views.attribute_activate, name="attribute-activate"),
    path("attributes/<int:pk>/delete/", views.attribute_delete, name="attribute-delete"),
    path("attributes/<int:pk>/values/", views.attribute_values, name="attribute-values"),
    path("attributes/<int:pk>/values/add/", views.attribute_value_add, name="attribute-value-add"),
    path("attributes/<int:pk>/values/<int:value_id>/archive/", views.attribute_value_archive, name="attribute-value-archive"),
    path("attributes/<int:pk>/values/<int:value_id>/delete/", views.attribute_value_delete, name="attribute-value-delete"),

    path("products/<int:pk>/options/", views.product_options, name="product-options"),
    path("products/<int:pk>/options/add/", views.product_option_add, name="product-option-add"),
    path("products/<int:pk>/options/recommended/<int:recommendation_id>/apply/", views.product_apply_recommended_option, name="product-apply-recommended-option"),
    path("products/<int:pk>/options/reorder/", views.product_options_reorder, name="product-options-reorder"),
    path("products/<int:pk>/options/<int:option_id>/move/", views.product_option_move, name="product-option-move"),
    path("products/<int:pk>/options/<int:option_id>/deactivate/", views.product_option_deactivate, name="product-option-deactivate"),
    path("products/<int:pk>/options/<int:option_id>/activate/", views.product_option_activate, name="product-option-activate"),
    path("products/<int:pk>/options/<int:option_id>/values/add/", views.product_option_value_add, name="product-option-value-add"),
    path("products/<int:pk>/options/values/<int:value_id>/remove/", views.product_option_value_remove, name="product-option-value-remove"),
    path("products/<int:pk>/options/generate/", views.product_variants_generate, name="product-variants-generate"),
    path("products/<int:pk>/options/variants/<int:variant_id>/default/", views.product_variant_set_default, name="product-variant-set-default"),
    path("products/<int:pk>/options/bulk-update/", views.product_variants_bulk_update, name="product-variants-bulk-update"),

    path("categories/", views.category_list, name="category-list"),
    path("categories/add-main/", views.category_add_main, name="category-add-main"),
    path("categories/add-sub/", views.category_add_sub, name="category-add-sub"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category-edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category-delete"),
    path("categories/<int:pk>/schema/", views.category_schema, name="category-schema"),
    path("categories/<int:pk>/schema/add/", views.category_schema_add, name="category-schema-add"),
    path("categories/<int:pk>/schema/<int:entry_id>/toggle-required/", views.category_schema_toggle_required, name="category-schema-toggle-required"),
    path("categories/<int:pk>/schema/<int:entry_id>/remove/", views.category_schema_remove, name="category-schema-remove"),
    path("categories/<int:pk>/schema/<int:entry_id>/move/", views.category_schema_move, name="category-schema-move"),

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
    path("settings/industry/<int:template_id>/install/", views.settings_industry_install, name="settings-industry-install"),
    path("settings/finance/", views.settings_finance, name="settings-finance"),
    path("settings/appearance/", views.settings_appearance, name="settings-appearance"),
    path("settings/gateways/<int:pk>/toggle/", views.settings_gateway_toggle, name="settings-gateway-toggle"),
    path("settings/shipping/<int:pk>/toggle/", views.settings_shipping_toggle, name="settings-shipping-toggle"),

    # --- Real gateway configuration (PR1) ---
    path("settings/gateway-config/<str:gateway_code>/save/", views.settings_gateway_config_save, name="settings-gateway-config-save"),
    path("settings/gateway-config/<str:gateway_code>/toggle/", views.settings_gateway_config_toggle, name="settings-gateway-config-toggle"),

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

    # --- شبکه‌های اجتماعی ---
    path("social-links/", views.social_link_list, name="social-link-list"),
    path("social-links/add/", views.social_link_form, name="social-link-add"),
    path("social-links/<int:pk>/edit/", views.social_link_form, name="social-link-edit"),
    path("social-links/<int:pk>/delete/", views.social_link_delete, name="social-link-delete"),
    path("social-links/<int:pk>/toggle/", views.social_link_toggle, name="social-link-toggle"),

    # --- مدیریت منوها ---
    path("menus/", views.menu_list, name="menu-list"),
    path("menus/add/", views.menu_form, name="menu-add"),
    path("menus/<int:pk>/edit/", views.menu_form, name="menu-edit"),
    path("menus/<int:pk>/delete/", views.menu_delete, name="menu-delete"),
    path("menus/<int:pk>/toggle/", views.menu_toggle, name="menu-toggle"),
    path("menus/<int:menu_id>/items/", views.menu_item_list, name="menu-item-list"),
    path("menus/<int:menu_id>/items/add/", views.menu_item_form, name="menu-item-add"),
    path("menu-items/<int:pk>/edit/", views.menu_item_form, name="menu-item-edit"),
    path("menu-items/<int:pk>/delete/", views.menu_item_delete, name="menu-item-delete"),
    path("menu-items/<int:pk>/toggle/", views.menu_item_toggle, name="menu-item-toggle"),

    # --- تنظیمات فوتر ---
    path("footer/settings/", views.footer_settings_page, name="footer-settings"),
    path("footer/trust-badges/", views.footer_trust_badge_list, name="footer-trust-badge-list"),
    path("footer/trust-badges/add/", views.footer_trust_badge_form, name="footer-trust-badge-add"),
    path("footer/trust-badges/<int:pk>/edit/", views.footer_trust_badge_form, name="footer-trust-badge-edit"),
    path("footer/trust-badges/<int:pk>/delete/", views.footer_trust_badge_delete, name="footer-trust-badge-delete"),
    path("footer/trust-badges/<int:pk>/toggle/", views.footer_trust_badge_toggle, name="footer-trust-badge-toggle"),
    path("footer/payment-logos/", views.footer_payment_logo_list, name="footer-payment-logo-list"),
    path("footer/payment-logos/add/", views.footer_payment_logo_form, name="footer-payment-logo-add"),
    path("footer/payment-logos/<int:pk>/edit/", views.footer_payment_logo_form, name="footer-payment-logo-edit"),
    path("footer/payment-logos/<int:pk>/delete/", views.footer_payment_logo_delete, name="footer-payment-logo-delete"),
    path("footer/payment-logos/<int:pk>/toggle/", views.footer_payment_logo_toggle, name="footer-payment-logo-toggle"),
]
