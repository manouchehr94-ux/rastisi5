"""تعریف رویدادهای پیامکی، متغیرهای مجاز هر رویداد، و متن پیش‌فرض قالب‌ها.

این ماژول تنها منبع حقیقت برای «کدام متغیر در کدام رویداد مجاز است» است؛ هم
اعتبارسنجی قالب (apps.sms.services.sms_service) و هم نمایش راهنما در پنل
مدیریت از همین دیکشنری‌ها می‌خوانند — چیزی در تمپلیت هاردکد نشده.
"""

from django.db import models


class SmsEvent(models.TextChoices):
    WELCOME = "welcome", "ثبت‌نام / خوش‌آمدگویی"
    OTP = "otp", "کد ورود یکبار مصرف"
    ORDER_PLACED = "order_placed", "ثبت سفارش"
    PAYMENT_SUCCESS = "payment_success", "پرداخت موفق"
    PAYMENT_FAILED = "payment_failed", "پرداخت ناموفق"
    ORDER_PROCESSING = "order_processing", "سفارش در حال پردازش"
    ORDER_SHIPPED = "order_shipped", "ارسال سفارش"
    ORDER_DELIVERED = "order_delivered", "تحویل سفارش"
    ORDER_CANCELED = "order_canceled", "لغو سفارش"


# متغیرهای مجاز هر رویداد: کد متغیر -> برچسب فارسی (برای راهنمای پنل مدیریت)
EVENT_VARIABLES: dict[str, dict[str, str]] = {
    SmsEvent.WELCOME: {"customer_name": "نام مشتری", "shop_name": "نام فروشگاه"},
    SmsEvent.OTP: {"otp_code": "کد یکبار مصرف", "shop_name": "نام فروشگاه"},
    SmsEvent.ORDER_PLACED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.PAYMENT_SUCCESS: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ پرداخت‌شده", "shop_name": "نام فروشگاه",
    },
    SmsEvent.PAYMENT_FAILED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_PROCESSING: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_SHIPPED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "tracking_code": "کد رهگیری مرسوله", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_DELIVERED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_CANCELED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
}

DEFAULT_TEMPLATES: dict[str, str] = {
    SmsEvent.WELCOME: "{customer_name} عزیز، به {shop_name} خوش آمدید! از این پس می‌توانید با کد یکبار مصرف هم وارد حساب خود شوید.",
    SmsEvent.OTP: "کد ورود شما به {shop_name}: {otp_code}\nاین کد تا ۲ دقیقه معتبر است.",
    SmsEvent.ORDER_PLACED: "{customer_name} عزیز، سفارش {order_code} به مبلغ {amount} تومان با موفقیت ثبت شد. {shop_name}",
    SmsEvent.PAYMENT_SUCCESS: "{customer_name} عزیز، پرداخت سفارش {order_code} به مبلغ {amount} تومان با موفقیت انجام شد. {shop_name}",
    SmsEvent.PAYMENT_FAILED: "{customer_name} عزیز، پرداخت سفارش {order_code} ناموفق بود. برای پیگیری به حساب کاربری خود مراجعه کنید. {shop_name}",
    SmsEvent.ORDER_PROCESSING: "{customer_name} عزیز، سفارش {order_code} شما در حال پردازش و بسته‌بندی است. {shop_name}",
    SmsEvent.ORDER_SHIPPED: "{customer_name} عزیز، سفارش {order_code} ارسال شد. کد رهگیری: {tracking_code} — {shop_name}",
    SmsEvent.ORDER_DELIVERED: "{customer_name} عزیز، سفارش {order_code} به شما تحویل داده شد. از خرید شما سپاسگزاریم. {shop_name}",
    SmsEvent.ORDER_CANCELED: "{customer_name} عزیز، سفارش {order_code} لغو شد. {shop_name}",
}
