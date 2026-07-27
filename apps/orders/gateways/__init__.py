"""Payment gateway adapter infrastructure.

This package implements the gateway adapter pattern for the payment domain.
Each real payment gateway (Zibal, future ZarinPal, etc.) is an independent
adapter that implements a common contract. Cash on Delivery is also modeled
as an adapter for uniform dispatch.

Architecture:
    PaymentGatewayAdapter (abstract contract)
    ├── ZibalAdapter        — online payment via Zibal API
    ├── CodAdapter          — Cash on Delivery (offline)
    └── (future adapters)

Registry:
    get_adapter(gateway_code) → adapter instance
    GATEWAY_CHOICES          → available codes for model field choices

Adapters never call each other. Checkout code dispatches through the registry
and never imports a specific adapter class directly.
"""

from .base import PaymentGatewayAdapter  # noqa: F401
from .registry import GATEWAY_CHOICES, get_adapter  # noqa: F401
