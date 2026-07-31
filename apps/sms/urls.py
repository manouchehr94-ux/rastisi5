from django.urls import path

from . import gateway_views

app_name = "sms"

urlpatterns = [
    # endpointِ عمومیِ گیت‌وی اندرویدِ SmsRasti (بدونِ CSRF، device_token-authenticated).
    path("smsrasti/poll/", gateway_views.smsrasti_poll, name="smsrasti-poll"),
    path("smsrasti/ack/", gateway_views.smsrasti_ack, name="smsrasti-ack"),
]
