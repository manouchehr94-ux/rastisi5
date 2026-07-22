from django.shortcuts import render

from .decorators import staff_required
from .services import dashboard_service
from .services.charts import build_line_chart_svg

VALID_RANGES = {"week", "month", "year"}


@staff_required
def dashboard_home(request):
    context = dashboard_service.build_dashboard_context()
    context["active_page"] = "dashboard"
    return render(request, "dashboard/dashboard.html", context)


@staff_required
def sales_chart_partial(request):
    range_key = request.GET.get("range", "month")
    if range_key not in VALID_RANGES:
        range_key = "month"
    data, labels = dashboard_service.sales_chart_data(range_key)
    svg = build_line_chart_svg(data, labels)
    return render(request, "dashboard/partials/sales_chart.html", {"svg": svg})
