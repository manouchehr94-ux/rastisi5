"""Cross-table hostname namespace guards for RastiSi-owned hosts.

Store.admin_subdomain and StoreDomain.hostname live in different tables,
so cross-table collisions are enforced by authoritative write services.
"""

from apps.stores.hostnames import rastisi_owned_domain_suffixes
from apps.stores.models import Store, StoreDomain


class DomainNamespaceCollisionError(Exception):
    """A RastiSi-owned hostname label belongs to a different Store."""


def _normalized_label(label: str) -> str:
    return str(label or "").strip().lower().strip(".")


def platform_owned_hosts_for_label(label: str) -> frozenset[str]:
    normalized = _normalized_label(label)
    return frozenset(
        f"{normalized}.{suffix}"
        for suffix in rastisi_owned_domain_suffixes()
        if normalized
    )


def assert_public_handle_namespace_available(*, store: Store, label: str) -> None:
    """Fail if label is the admin_subdomain of another Store."""
    normalized = _normalized_label(label)
    if not normalized:
        return
    collision = (
        Store.objects.exclude(pk=store.pk)
        .filter(admin_subdomain=normalized)
        .only("id", "admin_subdomain")
        .first()
    )
    if collision is not None:
        raise DomainNamespaceCollisionError(
            "این نام قبلاً برای آدرس مدیریت یک فروشگاه دیگر رزرو شده است."
        )


def assert_admin_subdomain_namespace_available(*, store: Store, label: str) -> None:
    """Fail if another Store already owns this platform-host label."""
    hosts = platform_owned_hosts_for_label(label)
    if not hosts:
        return

    queryset = StoreDomain.objects.filter(hostname__in=hosts)
    if store.pk is not None:
        queryset = queryset.exclude(store_id=store.pk)

    collision = queryset.only("id", "store_id", "hostname").first()
    if collision is not None:
        raise DomainNamespaceCollisionError(
            "این نام قبلاً برای آدرس عمومی یک فروشگاه دیگر در RastiSi رزرو شده است."
        )
