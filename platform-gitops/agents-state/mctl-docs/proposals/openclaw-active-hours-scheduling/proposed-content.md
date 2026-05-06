# Proposed content: openclaw-active-hours-scheduling

> **Apply to:** `mctl-docs/docs/platform/openclaw.md` (UPDATE)
> **Source:** mctl-openclaw@10448a0

---

## Diff: add "Agent scheduling: active hours" subsection

The subsection below should be inserted into `docs/platform/openclaw.md` after the
existing main content and before any "See also" / footer block. The exact insertion
point depends on the current page structure (read the file first).

<!-- TODO: confirm activeHours key syntax with author of mctl-openclaw@10448a0 before
     merging. The key name below (`activeHours`), the `start`/`end` format, and the
     `timezone` field name are inferred from source file names and PR description —
     verify against the actual JSON/YAML schema in `src/infra/heartbeat-active-hours.ts`
     or the OpenClaw config reference. -->

---

### After (new subsection to add)

```markdown
## Agent scheduling: active hours

OpenClaw agents can be restricted to a configurable window of active hours. Outside
this window the agent enters **quiet mode**: heartbeat ticks are skipped (not
accumulated) and outbound processing is paused until the next in-window phase slot.

### Configuring active hours

Add an `activeHours` block to the agent's configuration:

```yaml
# Example: agent active Mon–Fri, 09:00–18:00 Europe/Berlin
activeHours:
  start: "09:00"
  end: "18:00"
  timezone: "Europe/Berlin"
```

| Field | Type | Description |
|---|---|---|
| `start` | `HH:MM` (24-hour) | Start of the active window (local time) |
| `end` | `HH:MM` (24-hour) | End of the active window (local time) |
| `timezone` | IANA timezone string | Timezone for evaluating the window (e.g. `Asia/Shanghai`, `America/New_York`) |

> **Heartbeat alignment:** The heartbeat period (e.g. `4h`) is aligned to
> in-window phase slots. A quiet-hours slot is skipped entirely — the next
> tick fires at the first valid in-window slot after the quiet period ends.
> This means no burst of deferred work upon resumption.

### Behaviour when no active hours are set

If `activeHours` is omitted, the agent runs 24/7 with no scheduling restriction.
This is the default.

### Troubleshooting: agent appears silent

If your agent is not responding during expected hours:

1. Check that `activeHours.timezone` matches your local timezone exactly
   (use an [IANA timezone name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)).
2. Verify the `start`/`end` times use 24-hour format (`09:00`, not `9am`).
3. Confirm the agent deployment has reloaded its config after the change
   (a pod restart or config-reload signal is required).

See also: [Troubleshooting → Agent issues](/reference/troubleshooting#agent-issues).
```

---

## Diff: add cross-link to docs/reference/troubleshooting.md

Find the appropriate section in `docs/reference/troubleshooting.md` (e.g.
"Agent issues" or "OpenClaw") and add the following bullet:

### Before (representative excerpt — adjust to match actual page content)

```markdown
## Agent issues

- **Agent not responding** — check pod logs with `kubectl logs -n admins deploy/openclaw-agent`.
```

### After

```markdown
## Agent issues

- **Agent not responding** — check pod logs with `kubectl logs -n admins deploy/openclaw-agent`.
- **Agent silent during expected hours** — if the agent has `activeHours` configured,
  verify the `timezone` and `start`/`end` times are correct.
  See [Agent scheduling: active hours](/platform/openclaw#agent-scheduling-active-hours).
```
