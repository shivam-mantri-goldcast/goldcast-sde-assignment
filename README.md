# webhook-ingest

A service that ingests email delivery-event webhooks from multiple providers and
maintains the current delivery state of every message we have sent.

This document is the specification the service is built against. Your task is in
**`TASK.md`**.

---

## Context

We send transactional and campaign email through two providers. Each provider
notifies us by webhook as messages are delivered, opened, clicked, bounced or
reported as spam. Downstream systems — reporting, suppression lists, customer
dashboards — read the delivery state this service maintains, so its accuracy is
load-bearing.

---

## Functional requirements

### R1 — Normalise both providers

Payloads from Postmark and SES arrive in different shapes and must be reduced
to one canonical event before processing.

|                  | Postmark              | SES (via SNS)                          |
| ---------------- | --------------------- | -------------------------------------- |
| Message ID       | `MessageID`           | `mail.messageId`                       |
| Event type       | `RecordType`          | `eventType`                            |
| Payload shape    | flat JSON object      | `Message` is a JSON-encoded **string** |
| Timestamp        | ISO-8601 with offset  | ISO-8601 ending in `Z`                 |
| Bounce detail    | `Type`                | `bounce.bounceType`                    |
| Event identifier | `ID`                  | `bounce.feedbackId` / SNS `MessageId`  |

For SES the outer envelope is an SNS notification; the event itself sits inside
the `Message` field as a JSON string that must be parsed a second time.

Every event must resolve to a provider event identifier that is unique per
event, not per message. Where a payload does not carry an explicit identifier,
the identifier your service derives must still be unique per event.

### R2 — Maintain delivery state

```
queued → sent → delivered → opened
                          → clicked
```

`bounced_permanent`, `complained` and `dropped` are **terminal**. Once a message
reaches a terminal state, no subsequent event may move it out of that state.

Opens and clicks are repeatable and may arrive in either order. Neither
supersedes the other.

### R3 — Classify bounces correctly

A **permanent** bounce means the address is undeliverable. It is terminal and the
address should end up on a suppression list.

A **transient** bounce is a temporary failure — a full mailbox, a greylisting
delay, a downstream timeout. The provider will usually retry, and the message may
subsequently be delivered successfully. A transient bounce is **not** terminal and
must not prevent a later delivery from being recorded.

SES distinguishes these via `bounce.bounceType` (`Permanent` or `Transient`).
Postmark distinguishes them via `Type` (`HardBounce` and others).

### R4 — Process each distinct event exactly once

Providers retry on any non-2xx response, so the same event will sometimes be
delivered to us more than once. A repeat delivery of an event we have already
processed must not change stored state, and must be reported as a duplicate.

**Two deliveries represent the same event only when they carry the same provider
event identifier.** Message ID and event type alone do not establish identity —
a single message legitimately produces many events of the same type, and each is
a distinct event that must be recorded.

### R5 — Tolerate out-of-order arrival

Retries and provider-side queuing mean events do not necessarily arrive in the
order they occurred. A late-arriving event for an earlier lifecycle stage must not
regress a message that has already progressed past it.

### R6 — Reject malformed input safely

An unparseable body, an unknown provider, an unrecognised event type or a missing
required field must produce a `400` response. The service must never crash on bad
input, and a rejected event must leave stored state untouched.

---

## Operating conditions

The service runs as **multiple stateless workers behind a load balancer**, all
sharing one database. Any worker may receive any event; there is no affinity
between a message and a worker.

Observed production volume:

- **2,000–5,000 events/second sustained** across all messages during a campaign send
- **Bursts of 30–60 events for a single `message_id` within the same second.**
  This is normal: mail clients pre-fetch tracking pixels, corporate mail gateways
  scan links on delivery, and a message forwarded inside an organisation generates
  an open per viewer — all against the same message ID.
- Provider retry storms following any brief outage on our side, during which a
  large backlog of previously-delivered events is redelivered at once

**Every accepted event must be reflected in stored state.** Under concurrent
processing of events for the same message, no update may be lost.

---

## API contract

```python
WebhookService.handle_webhook(provider: str, raw_body: str) -> Response
```

| Outcome | Status | Body |
| --- | --- | --- |
| Event accepted and applied | 200 | `{"status": "ok", "state": "<delivery state>"}` |
| Event already processed | 200 | `{"status": "duplicate", "state": "<delivery state>"}` |
| Payload rejected | 400 | `{"error": "<reason>"}` |

Anything other than a 2xx causes the provider to retry.

---

## Running it

Requires Python 3.9+. No database setup, no external services.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

There is no HTTP server to start. `handle_webhook` is a plain function you can
call directly:

```python
import json
from app.api import WebhookService
from app.store import Store

svc = WebhookService(Store())

response = svc.handle_webhook("postmark", json.dumps({
    "RecordType": "Delivery",
    "MessageID": "msg-abc",
    "Recipient": "user@example.com",
    "DeliveredAt": "2026-01-15T10:23:41+00:00",
    "ID": "pm-delivery-1",
}))
print(response.status, response.body)

state, event_count = svc.store.get("msg-abc")
print(state, event_count)
```

Useful commands:

```bash
python -m pytest tests/ -k "bounce" -v          # filter by name
python -m pytest tests/test_visible.py -v       # the shipped suite
```

Sample payloads for both providers are in `fixtures/payloads/`.

---

## Layout

```
app/
  models.py      canonical event shape, DeliveryState enum
  normalize.py   provider payload → CanonicalEvent
  state.py       delivery state machine
  store.py       persistence and deduplication
  api.py         webhook entry point
tests/
  test_visible.py
fixtures/payloads/
```

---

## Using AI

AI use is expected and encouraged. Use whatever you normally use — ChatGPT,
Claude, Copilot, Cursor, or nothing at all.

- **This fits in a free tier.** The codebase is under 500 lines. You do not need
  a paid plan or an agentic tool.
- **Describe your use plainly.** "I had the model draft the fix and rewrote the
  test myself" is a fine answer.
- **You own what you submit.** If you cannot explain a decision in the debrief,
  it counts against you regardless of what produced it.

---

## What to submit

Start by reading **`TASK.md`** for the full brief. When done, zip your work
and submit it via the link you were given.

Your zip must include:

1. **Your code** — all changes to `app/` and any new test files under `tests/`.
2. **`DECISIONS.md`** — one page maximum. What you changed and why, what you
   assumed, what you would do next with more time, and anything the model got
   wrong that you caught.
3. **`TRANSCRIPT.md`** — your AI session pasted as-is. If you did not use AI,
   one line saying so is enough.

## Ground rules

- **Do not modify `tests/test_visible.py`.** Add your own tests in new files
  under `tests/`. Modifying the shipped file is an automatic disqualification.
- No new dependencies beyond `requirements.txt` without noting why.
- A partial solution you can explain beats a complete one you cannot. Write down
  what you would have done next if you didn't get to everything.

## After you submit

We will follow up to walk through a few of your decisions. No new coding,
no algorithm questions.
