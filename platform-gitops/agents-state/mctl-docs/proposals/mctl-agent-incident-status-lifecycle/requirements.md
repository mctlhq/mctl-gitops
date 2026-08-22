# Document the incident status lifecycle, including the new `escalated` state

## Context
`mctl-agent` shipped an 8-commit story across releases 1.16.0 and 1.16.1
(2026-08-15 to 2026-08-18, confirmed live via `mctl-gitops` commit
`d6e6679`) that gives escalated tickets a first-class `escalated` status,
distinct from `analyzing`:

- `4ab7e7d` — adds the `escalated` status, its own auto-resolve GC window
  (`AUTO_RESOLVE_ESCALATED_AFTER`, default 168h/7 days, same policy as
  `fix_proposed`), and a Prometheus metric label for it.
- `106ef91` — fixes the GC guard so configuring only
  `AUTO_RESOLVE_ESCALATED_AFTER` still runs the sweep (previously it would
  have silently no-opped).
- `60a9089` / `937c7c1` — fix status-transition ordering bugs around
  publishing to `mctl-api` and syncing `analyzing`.
- `8c4bb92` — fixes `fix_failed` being emitted *after* escalating instead
  of before (ordering bug).
- `67c0cc9` — closes remaining `analyzing`-state leaks.
- `e04153e` — sends `mctl-api` a full ticket snapshot on escalation and
  adds test coverage.

Anyone reading incident state through `mctl_list_incidents`,
`mctl_get_incident`, or `mctl_incident_summary` can now see `escalated` as
a value distinct from `analyzing`. This exposes a pre-existing gap: no
page on docs.mctl.ai enumerates incident status values at all — the new
status makes that gap concretely worse (a reader has even less chance of
guessing what `escalated` means without documentation, since it's not the
obvious "still working on it" meaning of `analyzing`).

## User stories
- AS a platform operator using `mctl_list_incidents` / `mctl_get_incident`
  I WANT to know what each status value means SO THAT I can correctly
  interpret incident state and know when human intervention is needed.
- AS a platform admin I WANT to know that `escalated` incidents
  auto-resolve after about a week of inactivity SO THAT I'm not surprised
  when an old escalated incident disappears from `mctl_list_incidents`.
- AS a reader I WANT `escalated` distinguished from `analyzing` SO THAT I
  don't assume the agent is still actively investigating when it has
  actually stopped and is waiting on a human.

## Acceptance criteria (EARS)
- WHEN a reader looks up incident status values THE SYSTEM SHALL list all
  values (`open`, `analyzing`, `escalated`, `fix_proposed`, `resolved`,
  `suppressed`, `acknowledged`) with a one-line meaning for each.
- IF a reader wants to know why an old escalated incident is no longer
  listed THEN THE SYSTEM SHALL state the default auto-resolve window
  (about 7 days of inactivity).
- WHILE describing `escalated` THE SYSTEM SHALL contrast it explicitly
  with `analyzing`: "diagnosed and handed to a human, not yet acted on"
  vs. "the agent is actively investigating."

## Out of scope
- A full state-machine diagram of every internal pipeline transition.
- Documenting agent-operator-only environment variables (e.g. the exact
  name and tuning of `AUTO_RESOLVE_ESCALATED_AFTER`) beyond the
  observable default behavior — those are deployment config for the
  platform team, not tenant/user-facing MCP documentation.
