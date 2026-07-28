# Payment Architecture — PR1 Foundation

> **Status:** Active
> **Introduced:** PR1 (Payment Domain Foundation)
> **Scope:** Zibal online payment, Cash on Delivery, per-store gateway configuration

---

## 1. Overview

The payment domain lives within the existing `apps.orders` application.
Payment concepts (gateway configuration, payment attempts, adapter dispatch)
are co-located with order models because they share the same lifecycle and
tenant boundary.

```
apps/orders/
├── models.py               ← PaymentGatewayConfig, PaymentAttempt (+ existing Order, Transaction)
├── encryption.py           ← Fernet-based credential encryption
├── gateways/
│   ├── __init__.py         ← Public API: get_adapter(), GATEWAY_CHOICES
│   ├── base.py             ← Abstract PaymentGatewayAdapter contract
│   ├── registry.py         ← Adapter registry and dispatch
│   ├── zibal.py            ← Zibal online payment adapter
│   └── cod.py              ← Cash on Delivery adapter
├── services/
│   ├── gateway_payment_service.py  ← Orchestrates real payment lifecycle
│   ├── payment_service.py          ← Legacy simulation (gated, unchanged)
│   └── ...
└── views.py                ← payment_initiate, gateway_callback (+ existing)
```

---

## 2. Gateway Adapter Contract

Every payment gateway implements `PaymentGatewayAdapter`:

```python
class PaymentGatewayAdapter(ABC):
    code: str                   # Unique code (e.g., "zibal", "cod")
    display_name: str           # Persian name for UI
    is_online: bool             # True = redirect flow; False = offline (COD)
    required_credentials: list  # Required credential field names

    def validate_credentials(credentials) -> list[str]
    def create_payment(...) -> PaymentCreationResult
    def build_redirect_url(track_id, ...) -> str
    def verify_payment(...) -> PaymentVerificationResult
```

Adapters are stateless. Configuration is passed per-call from the database.
New gateways are added by:
1. Creating `apps/orders/gateways/new_gateway.py`
2. Adding a loader to `registry.py`
3. Adding a choice to `PaymentGatewayConfig.GatewayCode`

No other code changes required.

---

## 3. Currency Boundary

| Layer | Unit | Notes |
|-------|------|-------|
| Database (Order, PaymentAttempt) | **Toman** | Integer-equivalent Decimal(0 places) |
| Checkout UI | **Toman** | Displayed with تومان suffix |
| Zibal API | **Rial** | 1 Toman = 10 Rial |
| Conversion point | **Inside ZibalAdapter only** | `amount_rial = int(amount) * 10` |

**Rule:** Toman→Rial conversion happens ONCE, inside the Zibal adapter.
No template, view, or service outside the adapter performs this conversion.
PaymentAttempt snapshots both `amount` and `currency` at creation time.

---

## 4. State Ownership

```
PaymentAttempt.status    → owned by gateway_payment_service
Order.payment_status     → updated by gateway_payment_service on success
Order.status             → transitions via order_service.change_order_status
```

### PaymentAttempt State Machine

```
CREATED → REQUESTING → REDIRECT_READY → PENDING → SUCCEEDED
                                                 → FAILED
                                                 → CANCELED
                                                 → EXPIRED
```

Terminal states: `SUCCEEDED`, `FAILED`, `CANCELED`, `EXPIRED`.

### Order Payment Status

```
PENDING → PAID       (on successful verification)
        → FAILED     (on all attempts failing — manual/future)
```

### Order Fulfillment Status

```
PENDING → PROCESSING (triggered by payment success)
        → SHIPPED → DELIVERED
        → CANCELED
```

**Inventory** is decremented at order creation (not at payment).
Payment success triggers `PENDING → PROCESSING` transition.

---

## 5. Zibal Payment Flow

```
1. Customer completes checkout
2. payment_start → payment_initiate (if real config exists)
3. gateway_payment_service.initiate_payment():
   a. Validate: order not paid, config active, credentials valid
   b. Create PaymentAttempt (CREATED → REQUESTING)
   c. Adapter.create_payment() — POST to Zibal /v1/request
   d. Store trackId, mark REDIRECT_READY
4. Browser redirects to https://gateway.zibal.ir/start/{trackId}
5. Customer pays on Zibal page
6. Zibal redirects to /checkout/gateway/callback/{attempt_public_id}/
7. gateway_callback view → process_callback_and_verify():
   a. Load attempt (no auth required — public callback)
   b. Check idempotency (already final = return)
   c. Check order not already paid
   d. Adapter.verify_payment() — POST to Zibal /v1/verify
   e. Verify amount matches
   f. On success: attempt=SUCCEEDED, order=PAID, Transaction created
   g. Transition order to PROCESSING
   h. SMS notification on commit
8. Redirect to payment result page
```

---

## 6. Cash on Delivery Flow

```
1. Customer selects COD at checkout
2. payment_initiate → initiate_payment()
3. COD adapter: no external call, attempt=SUCCEEDED immediately
4. Order.payment_status stays PENDING (paid on delivery)
5. Redirect to result page — shows "پرداخت در محل"
```

COD does NOT mark the order as `PAID`. The merchant confirms payment
through the order status transition `DELIVERED`.

---

## 7. Credential Encryption

- **Algorithm:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Key:** `PAYMENT_CREDENTIAL_KEY` environment variable
- **NOT** Django's `SECRET_KEY` (independent lifecycle)
- **Storage:** Encrypted JSON blob in `PaymentGatewayConfig.encrypted_credentials`
- **Display:** Credentials never shown in full in admin UI or logs
- **Rotation:** Changing the key requires re-entering all credentials

### Key provisioning

```bash
# Generate a new key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set in environment:
export PAYMENT_CREDENTIAL_KEY="<generated-key>"
```

- **Development/tests:** Automatic dev-only key when `DEBUG=True`
- **Production:** Missing key → immediate startup failure (fail-closed)

---

## 8. Concurrency and Idempotency

| Mechanism | Purpose |
|-----------|---------|
| `PaymentAttempt.idempotency_key` (unique constraint) | Prevents duplicate attempts |
| `PaymentAttempt.gateway_track_id` (unique constraint) | Prevents duplicate track IDs |
| `select_for_update()` in success path | Prevents double-paid transition |
| Conditional `Order.objects.filter(payment_status=PENDING).update(...)` | Race-safe paid transition |
| `attempt.is_final` check before verification | Idempotent duplicate callbacks |
| `Order.idempotency_key` (existing) | Prevents duplicate order creation |

### SQLite vs PostgreSQL

`select_for_update()` on SQLite is a no-op (entire DB locks on write).
Application-level guards (conditional updates, status checks) provide the
actual safety boundary that works on both backends. PostgreSQL adds
row-level locking as defense-in-depth.

---

## 9. Required Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PAYMENT_CREDENTIAL_KEY` | Production only | Dev key when DEBUG=True | Fernet encryption key for credentials |
| `PAYMENTS_SIMULATION_ENABLED` | No | Same as DEBUG | Gates legacy simulation flow |

---

## 10. Adding a New Gateway (Future)

1. Create `apps/orders/gateways/new_gateway.py` implementing `PaymentGatewayAdapter`
2. Add a loader function to `apps/orders/gateways/registry.py`
3. Add a `GatewayCode` choice to `PaymentGatewayConfig` model
4. Create a migration for the new choice
5. No other code changes needed — checkout, admin, and callback dispatch automatically

---

## 11. What This PR Does NOT Implement

- ZarinPal, Mellat, Tejarat, Saman, Pasargad
- Automatic refunds
- Settlement/reconciliation/accounting
- Wallets or stored payment methods
- Multiple acquiring accounts per gateway
- Installment payments
- Marketplace payment splitting
