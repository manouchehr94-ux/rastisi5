from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, InventoryReservation, Product, ProductVariant, StockMovement, Vendor
from apps.catalog.services.inventory_service import InsufficientStockError
from apps.catalog.services.reservation_service import (
    ReservationError,
    consume_inventory_reservation,
    expire_inventory_reservations,
    list_reservations,
    release_inventory_reservation,
    reserve_inventory,
)
from apps.stores.models import Store

from datetime import timedelta


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ReservationServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-resv")
        self.category = Category.objects.create(store=self.store, name="لوازم", slug="gear-resv")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کیف پول", slug="wallet-resv",
            sku="SKU-RESV1", price=Decimal("200000"), stock=10,
        )
        self.cart = Cart.objects.create()


class ReserveInventoryTests(ReservationServiceTestCase):
    def test_reserves_without_touching_on_hand(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=4, cart=self.cart)
        self.product.refresh_from_db()
        self.assertEqual(reservation.status, InventoryReservation.Status.ACTIVE)
        self.assertEqual(self.product.stock, 10)
        self.assertFalse(StockMovement.objects.filter(product=self.product).exists())

    def test_reduces_available_quantity_for_subsequent_reservations(self):
        reserve_inventory(store=self.store, product=self.product, quantity=7, cart=self.cart)
        with self.assertRaises(InsufficientStockError):
            reserve_inventory(store=self.store, product=self.product, quantity=4, cart=self.cart)

    def test_rejects_zero_or_negative_quantity(self):
        with self.assertRaises(ReservationError):
            reserve_inventory(store=self.store, product=self.product, quantity=0, cart=self.cart)

    def test_rejects_product_from_other_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="resv-other", status=Store.Status.ACTIVE)
        with self.assertRaises(ReservationError):
            reserve_inventory(store=other_store, product=self.product, quantity=1, cart=self.cart)

    def test_rejects_inactive_product(self):
        self.product.status = Product.Status.DRAFT
        self.product.save(update_fields=["status"])
        with self.assertRaises(ReservationError):
            reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart)

    def test_variant_stock_used_when_variant_given(self):
        variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز", stock=3,
        )
        reserve_inventory(store=self.store, product=self.product, variant=variant, quantity=3, cart=self.cart)
        with self.assertRaises(InsufficientStockError):
            reserve_inventory(store=self.store, product=self.product, variant=variant, quantity=1, cart=self.cart)

    def test_rejects_variant_belonging_to_different_product(self):
        other_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کوله", slug="bag-resv",
            sku="SKU-RESV2", price=Decimal("100000"), stock=5,
        )
        variant = ProductVariant.objects.create(
            product=other_product, store=self.store, attribute="رنگ", value="آبی", stock=5,
        )
        with self.assertRaises(ReservationError):
            reserve_inventory(store=self.store, product=self.product, variant=variant, quantity=1, cart=self.cart)

    def test_idempotency_key_returns_existing_reservation_without_double_reserving(self):
        first = reserve_inventory(
            store=self.store, product=self.product, quantity=6, cart=self.cart, idempotency_key="key-1",
        )
        second = reserve_inventory(
            store=self.store, product=self.product, quantity=6, cart=self.cart, idempotency_key="key-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(InventoryReservation.objects.filter(idempotency_key="key-1").count(), 1)
        # موجودی هنوز باید برای رزروِ دیگری در دسترس باشد (فقط یک رزرو ثبت شده).
        reserve_inventory(store=self.store, product=self.product, quantity=4, cart=self.cart)

    def test_default_ttl_sets_expiry(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart)
        self.assertIsNotNone(reservation.expires_at)
        self.assertGreater(reservation.expires_at, timezone.now())

    def test_no_ttl_leaves_expiry_null(self):
        reservation = reserve_inventory(
            store=self.store, product=self.product, quantity=1, cart=self.cart, ttl_minutes=None,
        )
        self.assertIsNone(reservation.expires_at)


class ConsumeInventoryReservationTests(ReservationServiceTestCase):
    def test_consume_decrements_stock_and_writes_movement(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=3, cart=self.cart)
        consume_inventory_reservation(reservation, order=None)
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)
        self.assertIsNotNone(reservation.consumed_at)
        movement = StockMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, -3)

    def test_consume_is_idempotent_on_retry(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=3, cart=self.cart)
        consume_inventory_reservation(reservation, order=None)
        consume_inventory_reservation(reservation, order=None)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 1)

    def test_cannot_consume_released_reservation(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=3, cart=self.cart)
        release_inventory_reservation(reservation)
        with self.assertRaises(ReservationError):
            consume_inventory_reservation(reservation, order=None)


class ReleaseInventoryReservationTests(ReservationServiceTestCase):
    def test_release_frees_available_quantity_without_touching_on_hand(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=7, cart=self.cart)
        release_inventory_reservation(reservation)
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)
        self.assertIsNotNone(reservation.released_at)
        # موجودیِ آزادشده دوباره قابلِ رزرو است.
        reserve_inventory(store=self.store, product=self.product, quantity=7, cart=self.cart)

    def test_cannot_release_consumed_reservation(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=3, cart=self.cart)
        consume_inventory_reservation(reservation, order=None)
        with self.assertRaises(ReservationError):
            release_inventory_reservation(reservation)

    def test_cannot_release_already_released_reservation(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=3, cart=self.cart)
        release_inventory_reservation(reservation)
        with self.assertRaises(ReservationError):
            release_inventory_reservation(reservation)


class ExpireInventoryReservationsTests(ReservationServiceTestCase):
    def test_expires_only_active_reservations_past_expiry(self):
        expired = reserve_inventory(store=self.store, product=self.product, quantity=2, cart=self.cart, ttl_minutes=10)
        InventoryReservation.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        still_valid = reserve_inventory(store=self.store, product=self.product, quantity=2, cart=self.cart, ttl_minutes=10)

        count = expire_inventory_reservations()

        expired.refresh_from_db()
        still_valid.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(expired.status, InventoryReservation.Status.EXPIRED)
        self.assertEqual(still_valid.status, InventoryReservation.Status.ACTIVE)

    def test_expiring_frees_available_quantity(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=10, cart=self.cart, ttl_minutes=10)
        InventoryReservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        expire_inventory_reservations()
        reserve_inventory(store=self.store, product=self.product, quantity=10, cart=self.cart)

    def test_no_expired_reservations_returns_zero(self):
        reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart, ttl_minutes=10)
        self.assertEqual(expire_inventory_reservations(), 0)

    def test_reservations_without_expiry_never_expire(self):
        reservation = reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart, ttl_minutes=None)
        self.assertEqual(expire_inventory_reservations(), 0)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, InventoryReservation.Status.ACTIVE)

    def test_batches_across_multiple_pages(self):
        for _ in range(5):
            product = Product.objects.create(
                store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug=f"item-{_}",
                sku=f"SKU-BATCH{_}", price=Decimal("1000"), stock=5,
            )
            reservation = reserve_inventory(store=self.store, product=product, quantity=1, cart=self.cart, ttl_minutes=10)
            InventoryReservation.objects.filter(pk=reservation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        count = expire_inventory_reservations(batch_size=2)
        self.assertEqual(count, 5)


class ListReservationsTests(ReservationServiceTestCase):
    def test_filters_by_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="resv-list-other", status=Store.Status.ACTIVE)
        reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart)
        results = list_reservations(other_store)
        self.assertEqual(results.count(), 0)

    def test_filters_by_status(self):
        active = reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart)
        released = reserve_inventory(store=self.store, product=self.product, quantity=1, cart=self.cart)
        release_inventory_reservation(released)
        results = list_reservations(self.store, status=InventoryReservation.Status.ACTIVE)
        self.assertEqual(list(results), [active])
