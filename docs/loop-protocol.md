# LOOP Protocol

The SDK loop is:

```text
Observe repository state
 -> choose highest-priority unblocked task
 -> execute through an agent adapter
 -> verify through the harness
 -> record evidence
 -> update task/spec/decision state
 -> repeat
```

The loop stops only for explicit human gates, unavailable credentials, production
impact, contradictory acceptance criteria, missing tools for required evidence,
or no unblocked tasks.

Retry budget: the same repair path should not be repeated more than three times
without recording the blocker and switching to another unblocked investigation.
