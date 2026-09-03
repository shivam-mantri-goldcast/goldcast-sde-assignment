"""Visible test suite. These pass against the code as shipped."""
import json

import pytest

from app.api import WebhookService
from app.models import DeliveryState
from app.normalize import normalize
from app.store import Store


@pytest.fixture
def svc():
    return WebhookService(Store())


def postmark(record_type, message_id="msg-1", **extra):
    body = {
        "RecordType": record_type,
        "MessageID": message_id,
        "Recipient": "user@example.com",
        "DeliveredAt": "2026-01-15T10:23:41+00:00",
        "ID": f"pm-{record_type}-{message_id}",
    }
    body.update(extra)
    return json.dumps(body)


def ses(event_type, message_id="msg-1", inner_extra=None):
    inner = {
        "eventType": event_type,
        "mail": {
            "messageId": message_id,
            "timestamp": "2026-01-15T10:23:41.000Z",
            "destination": ["user@example.com"],
        },
    }
    if inner_extra:
        inner.update(inner_extra)
    return json.dumps({"Type": "Notification", "MessageId": f"sns-{message_id}",
                       "Message": json.dumps(inner)})


def test_postmark_delivery(svc):
    resp = svc.handle_webhook("postmark", postmark("Delivery"))
    assert resp.status == 200
    assert resp.body["state"] == DeliveryState.DELIVERED.value


def test_ses_delivery(svc):
    resp = svc.handle_webhook("ses", ses("Delivery", "msg-2"))
    assert resp.status == 200
    assert resp.body["state"] == DeliveryState.DELIVERED.value


def test_ses_permanent_bounce_is_terminal(svc):
    svc.handle_webhook("ses", ses("Bounce", "msg-3",
                                  {"bounce": {"bounceType": "Permanent",
                                              "feedbackId": "fb-1"}}))
    state, _ = svc.store.get("msg-3")
    assert state == DeliveryState.BOUNCED_PERMANENT


def test_terminal_state_is_not_left(svc):
    svc.handle_webhook("ses", ses("Bounce", "msg-4",
                                  {"bounce": {"bounceType": "Permanent",
                                              "feedbackId": "fb-2"}}))
    svc.handle_webhook("postmark", postmark("Delivery", "msg-4"))
    state, _ = svc.store.get("msg-4")
    assert state == DeliveryState.BOUNCED_PERMANENT


def test_open_after_delivery_advances_state(svc):
    svc.handle_webhook("postmark", postmark("Delivery", "msg-5"))
    svc.handle_webhook("postmark", postmark("Open", "msg-5"))
    state, _ = svc.store.get("msg-5")
    assert state == DeliveryState.OPENED


def test_late_sent_does_not_regress_delivered(svc):
    svc.handle_webhook("postmark", postmark("Delivery", "msg-6"))
    svc.handle_webhook("ses", ses("Send", "msg-6"))
    state, _ = svc.store.get("msg-6")
    assert state == DeliveryState.DELIVERED


def test_retried_identical_event_is_deduplicated(svc):
    svc.handle_webhook("postmark", postmark("Delivery", "msg-7"))
    resp = svc.handle_webhook("postmark", postmark("Delivery", "msg-7"))
    assert resp.body["status"] == "duplicate"


def test_unknown_provider_rejected(svc):
    resp = svc.handle_webhook("mailgun", "{}")
    assert resp.status == 400


def test_malformed_json_rejected(svc):
    resp = svc.handle_webhook("postmark", "not json")
    assert resp.status == 400


def test_normalize_extracts_recipient():
    event = normalize("postmark", postmark("Delivery"))
    assert event.recipient == "user@example.com"
