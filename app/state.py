"""Delivery state machine.

Rules:
  * terminal states are never left
  * progress never goes backwards (a late "sent" cannot undo "delivered")
  * opens and clicks are repeatable and may arrive in either order
"""
from .models import DeliveryState, EventType, TERMINAL_STATES

# Higher rank means further along the lifecycle. Events that would move a
# message to a lower rank are late-arriving duplicates and are ignored.
_RANK = {
    DeliveryState.QUEUED: 0,
    DeliveryState.SENT: 1,
    DeliveryState.BOUNCED_TRANSIENT: 1,
    DeliveryState.DELIVERED: 2,
    DeliveryState.OPENED: 3,
    DeliveryState.CLICKED: 3,
}

_EVENT_TO_STATE = {
    EventType.SENT: DeliveryState.SENT,
    EventType.DELIVERED: DeliveryState.DELIVERED,
    EventType.OPENED: DeliveryState.OPENED,
    EventType.CLICKED: DeliveryState.CLICKED,
    EventType.COMPLAINED: DeliveryState.COMPLAINED,
    EventType.DROPPED: DeliveryState.DROPPED,
}


def next_state(current, event):
    """Return the state a message should be in after applying `event`."""
    if current in TERMINAL_STATES:
        return current

    if event.event_type is EventType.BOUNCED:
        if event.bounce_is_permanent:
            return DeliveryState.BOUNCED_PERMANENT
        return DeliveryState.BOUNCED_TRANSIENT

    target = _EVENT_TO_STATE.get(event.event_type)
    if target is None:
        return current

    if target in TERMINAL_STATES:
        return target

    if _RANK.get(target, 0) < _RANK.get(current, 0):
        return current
    return target
