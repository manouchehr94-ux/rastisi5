from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import AuditLogEntry
from apps.core.services.audit_service import list_audit_events, record_audit_event
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RecordAuditEventTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.actor = User.objects.create_user(username="09126600001", password="pass12345", is_staff=True)

    def test_creates_entry_with_expected_fields(self):
        entry = record_audit_event(
            store=self.store, actor=self.actor, action_code="test.action",
            object_type="Widget", object_id=42, object_label="ابزارِ نمونه",
            before={"stock": 5}, after={"stock": 8},
        )
        self.assertEqual(entry.action_code, "test.action")
        self.assertEqual(entry.object_id, "42")
        self.assertEqual(entry.result, AuditLogEntry.ResultStatus.SUCCESS)
        self.assertIn("5", entry.before_summary)
        self.assertIn("8", entry.after_summary)

    def test_redacts_forbidden_keys_in_metadata(self):
        entry = record_audit_event(
            store=self.store, actor=self.actor, action_code="test.secret",
            metadata={"password": "hunter2", "note": "ok"},
        )
        self.assertEqual(entry.metadata["password"], "***REDACTED***")
        self.assertEqual(entry.metadata["note"], "ok")

    def test_redacts_forbidden_keys_in_before_after(self):
        entry = record_audit_event(
            store=self.store, actor=self.actor, action_code="test.secret2",
            before={"api_key": "sk-live-123"}, after={"api_key": "sk-live-456"},
        )
        self.assertNotIn("sk-live", entry.before_summary)
        self.assertNotIn("sk-live", entry.after_summary)

    def test_no_actor_allowed_for_system_events(self):
        entry = record_audit_event(store=self.store, action_code="system.event")
        self.assertIsNone(entry.actor)

    def test_duplicate_request_id_does_not_create_second_row(self):
        first = record_audit_event(store=self.store, actor=self.actor, action_code="test.retry", request_id="req-1")
        second = record_audit_event(store=self.store, actor=self.actor, action_code="test.retry", request_id="req-1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="test.retry").count(), 1)

    def test_different_request_id_creates_new_row(self):
        record_audit_event(store=self.store, actor=self.actor, action_code="test.retry2", request_id="req-a")
        record_audit_event(store=self.store, actor=self.actor, action_code="test.retry2", request_id="req-b")
        self.assertEqual(AuditLogEntry.objects.filter(action_code="test.retry2").count(), 2)

    def test_failure_result_recorded(self):
        entry = record_audit_event(
            store=self.store, actor=self.actor, action_code="test.failure",
            result=AuditLogEntry.ResultStatus.FAILURE,
        )
        self.assertEqual(entry.result, AuditLogEntry.ResultStatus.FAILURE)


class ListAuditEventsTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.actor = User.objects.create_user(username="09126600002", password="pass12345", is_staff=True)

    def test_filters_by_store(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="audit-other", status=Store.Status.ACTIVE)
        record_audit_event(store=self.store, actor=self.actor, action_code="a.one")
        record_audit_event(store=other_store, actor=self.actor, action_code="a.one")
        events = list_audit_events(self.store)
        self.assertEqual(events.count(), 1)

    def test_filters_by_action_code(self):
        record_audit_event(store=self.store, actor=self.actor, action_code="a.one")
        record_audit_event(store=self.store, actor=self.actor, action_code="a.two")
        events = list_audit_events(self.store, action_code="a.one")
        self.assertEqual(events.count(), 1)

    def test_filters_by_search_term(self):
        record_audit_event(store=self.store, actor=self.actor, action_code="a.one", object_label="مشخصِ جستجو")
        record_audit_event(store=self.store, actor=self.actor, action_code="a.two", object_label="چیزِ دیگر")
        events = list_audit_events(self.store, q="جستجو")
        self.assertEqual(events.count(), 1)
