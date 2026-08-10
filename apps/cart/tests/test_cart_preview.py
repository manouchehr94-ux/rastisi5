"""تست‌هایِ موتورِ پیش‌نمایشِ سبد — count_link و mini_cart modes."""

from django.test import TestCase, RequestFactory

from apps.cart.services.cart_preview import (
    CART_PREVIEW_MODE_COUNT_LINK,
    CART_PREVIEW_MODE_MINI_CART,
    CART_PREVIEW_MODES,
    get_cart_preview_data,
)


class CartPreviewModeTests(TestCase):
    """حالت‌های پیش‌نمایش سبد."""

    def test_modes_enum(self):
        self.assertEqual(CART_PREVIEW_MODE_COUNT_LINK, "count_link")
        self.assertEqual(CART_PREVIEW_MODE_MINI_CART, "mini_cart")
        self.assertEqual(len(CART_PREVIEW_MODES), 2)

    def test_empty_cart_count_link(self):
        """بدون سبد: mode=count_link."""
        request = self._anonymous_request()
        data = get_cart_preview_data(request, mode=CART_PREVIEW_MODE_COUNT_LINK)
        self.assertTrue(data["cart_is_empty"])
        self.assertEqual(data["cart_count"], 0)
        self.assertEqual(data["cart_items_preview"], [])
        self.assertEqual(data["cart_preview_mode"], "count_link")

    def test_empty_cart_mini_cart(self):
        """بدون سبد: mode=mini_cart."""
        request = self._anonymous_request()
        data = get_cart_preview_data(request, mode=CART_PREVIEW_MODE_MINI_CART)
        self.assertTrue(data["cart_is_empty"])
        self.assertEqual(data["cart_count"], 0)
        self.assertEqual(data["cart_items_preview"], [])
        self.assertEqual(data["cart_preview_mode"], "mini_cart")

    def _anonymous_request(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        request.session = type("FakeSession", (), {"session_key": None})()
        return request


class CartPreviewURLTests(TestCase):
    """URL endpoint پیش‌نمایش سبد."""

    def test_preview_url_exists(self):
        """مسیر /cart/preview/ باید وجود داشته باشد."""
        from django.urls import reverse, NoReverseMatch

        try:
            url = reverse("cart:preview")
            self.assertEqual(url, "/cart/preview/")
        except NoReverseMatch:
            self.fail("cart:preview URL is not registered")
