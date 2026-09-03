"""Turn provider-specific webhook payloads into CanonicalEvent.

Two providers are supported today:

  postmark  flat JSON, "RecordType" names the event
  ses       SNS envelope; the "Message" field is a JSON-encoded *string*
            that has to be parsed a second time
"""
import json
from datetime import datetime, timezone

from .models import CanonicalEvent, EventType, NormalizationError

POSTMARK_TYPES = {
    "Delivery": EventType.DELIVERED,
    "Bounce": EventType.BOUNCED,
    "Open": EventType.OPENED,
    "Click": EventType.CLICKED,
    "SpamComplaint": EventType.COMPLAINED,
}

SES_TYPES = {
    "Send": EventType.SENT,
    "Delivery": EventType.DELIVERED,
    "Bounce": EventType.BOUNCED,
    "Open": EventType.OPENED,
    "Click": EventType.CLICKED,
    "Complaint": EventType.COMPLAINED,
}


def _parse_ts(raw):
    if raw is None:
        raise NormalizationError("missing timestamp")
    try:
        # Accepts both "+00:00" (Postmark) and "Z" (SES) suffixes.
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise NormalizationError(f"bad timestamp: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_postmark(payload):
    record_type = payload.get("RecordType")
    if record_type not in POSTMARK_TYPES:
        raise NormalizationError(f"unknown Postmark RecordType: {record_type!r}")

    message_id = payload.get("MessageID")
    if not message_id:
        raise NormalizationError("missing MessageID")

    event_type = POSTMARK_TYPES[record_type]
    is_permanent = None
    if event_type is EventType.BOUNCED:
        # Postmark reports hard bounces with Type "HardBounce".
        is_permanent = payload.get("Type") == "HardBounce"

    return CanonicalEvent(
        message_id=message_id,
        event_type=event_type,
        provider="postmark",
        provider_event_id=str(payload.get("ID") or f"{message_id}:{record_type}"),
        occurred_at=_parse_ts(payload.get("DeliveredAt") or payload.get("ReceivedAt")),
        recipient=payload.get("Recipient"),
        bounce_is_permanent=is_permanent,
    )


def _normalize_ses(envelope):
    raw_inner = envelope.get("Message")
    if raw_inner is None:
        raise NormalizationError("missing SNS Message")
    try:
        inner = json.loads(raw_inner) if isinstance(raw_inner, str) else raw_inner
    except json.JSONDecodeError as exc:
        raise NormalizationError("SNS Message is not valid JSON") from exc

    ses_type = inner.get("eventType")
    if ses_type not in SES_TYPES:
        raise NormalizationError(f"unknown SES eventType: {ses_type!r}")

    mail = inner.get("mail") or {}
    message_id = mail.get("messageId")
    if not message_id:
        raise NormalizationError("missing mail.messageId")

    event_type = SES_TYPES[ses_type]
    is_permanent = None
    event_id = envelope.get("MessageId") or f"{message_id}:{ses_type}"

    if event_type is EventType.BOUNCED:
        bounce = inner.get("bounce") or {}
        event_id = bounce.get("feedbackId") or event_id
        is_permanent = bounce.get("bounceType") == "Permanent"

    destinations = mail.get("destination") or []
    return CanonicalEvent(
        message_id=message_id,
        event_type=event_type,
        provider="ses",
        provider_event_id=str(event_id),
        occurred_at=_parse_ts(mail.get("timestamp")),
        recipient=destinations[0] if destinations else None,
        bounce_is_permanent=is_permanent,
    )


def normalize(provider, raw_body):
    """raw_body may be a JSON string or an already-decoded dict."""
    try:
        payload = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
    except json.JSONDecodeError as exc:
        raise NormalizationError("body is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise NormalizationError("body must be a JSON object")

    if provider == "postmark":
        return _normalize_postmark(payload)
    if provider == "ses":
        return _normalize_ses(payload)
    raise NormalizationError(f"unsupported provider: {provider!r}")
