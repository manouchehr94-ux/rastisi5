from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    # قبل از الگویِ عمومیِ <slug:slug>/ زیر — وگرنه هرگز به آن نمی‌رسد
    # (Django مسیرها را به ترتیبِ تعریف تطبیق می‌دهد).
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter-subscribe"),
    path("<slug:slug>/", views.page_detail, name="page-detail"),
]
