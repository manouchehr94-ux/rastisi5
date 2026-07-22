from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="dashboard"),
    path("sales-chart/", views.sales_chart_partial, name="sales-chart"),

    path("products/", views.product_list, name="product-list"),
    path("products/table/", views.product_table, name="product-table"),
    path("products/add/", views.product_form, name="product-add"),
    path("products/<int:pk>/edit/", views.product_form, name="product-edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product-delete"),

    path("categories/", views.category_list, name="category-list"),
    path("categories/add-main/", views.category_add_main, name="category-add-main"),
    path("categories/add-sub/", views.category_add_sub, name="category-add-sub"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category-edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category-delete"),
]
