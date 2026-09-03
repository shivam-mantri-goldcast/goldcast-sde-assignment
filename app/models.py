"""Canonical domain model shared by all providers."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class DeliveryState(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED_TRANSIENT = "bounced_transient"
    BOUNCED_PERMANENT = "bounced_permanent"
    COMPLAINED = "complained"
    DROPPED = "dropped"


# A message in a terminal state never changes again.
TERMINAL_STATES = frozenset({
    DeliveryState.BOUNCED_PERMANENT,
    DeliveryState.COMPLAINED,
    DeliveryState.DROPPED,
})


class EventType(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    DROPPED = "dropped"


@dataclass(frozen=True)
class CanonicalEvent:
    """A provider event, normalised into one shape."""
    message_id: str
    event_type: EventType
    provider: str
    provider_event_id: str
    occurred_at: datetime
    recipient: Optional[str] = None
    # Only meaningful when event_type is BOUNCED.
    bounce_is_permanent: Optional[bool] = None


@dataclass
class Response:
    status: int
    body: dict


class NormalizationError(ValueError):
    """Raised when a payload cannot be understood."""
