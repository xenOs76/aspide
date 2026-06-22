---
name: circuitpython-monotonic-ns
description: >-
  Prefer time.monotonic_ns() over time.monotonic() for long-interval periodic
  timers in CircuitPython firmware. Use when adding interval-based background
  checks, watchdogs, phone-home polls, or any timer spanning minutes or hours.
---

# CircuitPython long-interval timing

## Rule

Use `time.monotonic_ns()` for periodic checks over long intervals (minutes or
hours). It is reported to be more regular over long intervals of time than
`time.monotonic()` (float seconds), which can drift or lose precision on
extended runs.

## Pattern

Store timestamps and thresholds in **nanoseconds**:

```python
import time

INTERVAL_NS = interval_seconds * 1_000_000_000
last_check = time.monotonic_ns()

# In main loop:
if time.monotonic_ns() - last_check >= INTERVAL_NS:
    last_check = time.monotonic_ns()
    do_periodic_work()
```

Config keys may stay in seconds; convert once at init:

```python
PHONE_HOME_INTERVAL_NS = int(os.getenv("HA_PHONE_HOME_INTERVAL", 300)) * 1_000_000_000
```

## When to use which

| Use case | Clock | Why |
| --- | --- | --- |
| Long periodic tasks (≥ 1 min) | `monotonic_ns()` | Stable over long uptime |
| Sub-second gesture timing | `monotonic_ns()` | Already used in `ButtonPush` |
| Short second-scale UI timeout (~30 s) | `monotonic()` | Acceptable; existing `InactivityTimer` |

Prefer `monotonic_ns()` for **new** long-interval timers. Do not refactor
existing short timers unless changing that code anyway.

## Aspide examples

- **Phone-home HA check** (`code.py`): 5-minute gate with `HA_PHONE_HOME_INTERVAL_NS`
- **Button pushes** (`utils.py` `ButtonPush`): press/release thresholds in ns

## Anti-patterns

```python
# Bad for 30-minute intervals — float subtraction over long uptime
last = time.monotonic()
if time.monotonic() - last >= 1800:
    ...

# Good
last = time.monotonic_ns()
if time.monotonic_ns() - last >= 1800 * 1_000_000_000:
    ...
```
