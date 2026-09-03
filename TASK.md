# Task: Debug

Several production issues have been reported against this service. The shipped
test suite is green. Investigate the reports below, find the root causes, fix
them, and add tests that would have caught each problem.

Find as many as you can in the time you have. Be clear in `DECISIONS.md` about
what you found, what you suspect but haven't confirmed, and what you'd look at
next with more time.

---

## Reported issues

**From the deliverability team:**

> We ran a re-engagement campaign last week targeting 80K lapsed users. Our
> suppression list grew by 6,200 addresses — roughly 3× the expected rate for
> this audience. The affected addresses are still receiving mail from other
> ESPs so the addresses themselves are not dead. Something is putting them on
> the list incorrectly.

Suppression is triggered when a message reaches `bounced_permanent` state.

---

**From the customer success team:**

> A handful of customers who filed a spam complaint about last month's
> campaign received two separate apology/follow-up emails from our outreach
> team for what should have been a single complaint. Support pulled the raw
> event logs and only found one complaint webhook per customer — so whatever
> triggered the second email happened on our side, not the provider's.

---

**From the data engineering team:**

> Our nightly reconciliation job compares final delivery states against the
> raw provider event logs. On high-volume campaign days, we see a consistent
> discrepancy: the `event_count` stored for busy messages is lower than the
> number of events the providers actually delivered. The gap is proportional
> to volume — quiet days are fine, big sends are off by 5–15%. The events
> are not missing from the provider logs, so they reached us.

---

**From the on-call engineer:**

> During a brief database blip last Tuesday, a handful of webhook requests
> failed with a 500. The providers retried those exact requests a few seconds
> later, as expected. But checking afterward, none of the retried events ever
> made it into delivery state — they're just gone. The retry came back with a
> `200`, so from the provider's side everything looks fine.

---

**From the data engineering team (follow-up):**

> A separate reconciliation run flagged Postmark bounce counts specifically.
> Some messages received two transient bounce notifications from Postmark —
> visible in Postmark's activity log — but our store only shows
> `event_count: 1`. Postmark's payloads for both events look structurally
> identical except for the timestamp.

---

## What to do

1. Read `README.md` — it is the specification this service is built against.
   Pay attention to all sections, including the operating conditions and the
   API contract.
2. Investigate each report. The reports describe business impact; the root
   cause is in the code.
3. Fix what you find.
4. For each fix, add at least one test in a new file under `tests/` that
   **fails on the original code** and passes on your fix. We run your tests
   against the unfixed code mechanically — they must fail there to count.

## In `DECISIONS.md`

- For each issue you resolved: root cause, location in the code, which
  requirement in the spec it violates, and how you found it.
- For anything you suspected but didn't confirm: say so, and what you'd check
  next.
- What would have caught each before it reached production?
- Which defects did AI find on its own and which required you to direct it?
- What did you verify rather than take on trust?
