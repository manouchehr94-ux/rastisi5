"""Restricts Django Admin (``/admin/``) to active superusers only.

ADR-8 (see ``docs/architecture/SAAS_DOMAIN_DECISIONS.md``) records unscoped
Django-Admin access to Store-owned commerce data as a known, deferred
security boundary — it was never an accepted tenant-safe authorization
model. Before catalog models gained a real, multi-Store ``store`` FK, this
gap was latent (only one Store's data ever existed). Now that it does not,
this module closes the gap the minimal way: by refusing ``has_permission``
to anyone who is not an active superuser.

This does NOT change the merchant dashboard (``apps.dashboard``, gated by
``is_staff`` via ``apps.dashboard.decorators.staff_required``) — a Store's
own dashboard staff continue to use the dashboard exactly as before; they
simply can no longer also reach ``/admin/`` and its unscoped catalog
querysets. Full Store-aware Django Admin scoping, and wiring
``StoreMembership`` into dashboard authorization, remain deferred (PR 11).

Patched on the one, true ``django.contrib.admin.site`` singleton — every
``@admin.register(...)`` call across every app (``apps.catalog``,
``apps.stores``, ``apps.orders``, ``apps.blog``, ``apps.customers``,
``apps.cart``, ...) registers onto this same instance by default (no app
passes an explicit ``site=`` kwarg), so patching this one object is the
single, central, authoritative gate — no per-``ModelAdmin`` changes, no new
``AdminSite`` subclass, no change to ``shop_core/urls.py``'s
``admin.site.urls`` mount.
"""

from django.contrib import admin


def _superuser_only_has_permission(request):
    """The entire admin authorization boundary: active superusers only."""
    user = getattr(request, "user", None)
    return bool(user and user.is_active and user.is_superuser)


def install():
    admin.site.has_permission = _superuser_only_has_permission
