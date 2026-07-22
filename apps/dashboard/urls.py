from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="dashboard"),
    path("sales-chart/", views.sales_chart_partial, name="sales-chart"),
]
