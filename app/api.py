"""Webhook entry point.

Deliberately framework-free: `handle_webhook` is a plain function so the
service can be exercised without running a server. Wiring it to Flask or
FastAPI is a two-line exercise and is not part of any task.
"""
from .models import NormalizationError, Response
from .normalize import normalize
from .store import Store


class WebhookService:
    def __init__(self, store=None):
        self.store = store or Store()

    def handle_webhook(self, provider, raw_body):
        try:
            event = normalize(provider, raw_body)
        except NormalizationError as exc:
            return Response(400, {"error": str(exc)})

        if self.store.is_duplicate(event):
            state, _ = self.store.get(event.message_id)
            return Response(200, {"status": "duplicate", "state": state.value})

        self.store.record_seen(event)
        state = self.store.apply_event(event)
        return Response(200, {"status": "ok", "state": state.value})
