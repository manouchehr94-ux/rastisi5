from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    # endpointِ عمومیِ Webhook (بدونِ CSRF، امضا-تأییدشده).
    path("webhook/<slug:provider_code>/", views.billing_webhook, name="webhook"),
]
