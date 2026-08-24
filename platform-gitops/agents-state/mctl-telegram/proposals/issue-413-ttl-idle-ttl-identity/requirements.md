# Extend SESSION_TTL_EXEMPT_TG_IDS to cover the idle TTL, not just the absolute TTL

## Context

`SESSION_TTL_EXEMPT_TG_IDS` (introduced in #410, live since 0.51.0) was meant
to let long-lived operator/service Telegram identities skip session TTL
enforcement entirely, so they never need an interactive phone+SMS reconnect.
The implementation only lifts the **absolute** 90-day ceiling: `Store.SaveSession`
stamps `expires_at = NULL` for an exempt id, and every absolute-TTL reader
(`CheckSessionValid`, `SweepAbsoluteSessions`, `ListIdentities`) already treats
NULL as "never expires", so that half worked for free.

The **idle** 30-day TTL was never touched. `SweepIdleSessions` revokes on
`last_used_at < now - 30d` with no awareness of the exempt list at all, and
the idle branch of `CheckSessionValid` has the same blind spot. An exempt
identity that genuinely goes unused for a month (which is exactly the
scenario the exemption exists to survive — a demo/reviewer/service account
between uses) still gets silently revoked. The comment in
`internal/config/config.go` even documents this as intentional
("The 30-day idle TTL still applies to them"), and `TestIdleTTLStillAppliesToExempt`
in `internal/db/store_ttl_test.go` pins it as current, tested behavior — but
the issue argues this defeats the entire purpose of the exemption for any
identity that is not touched by *something* every month.

This is not theoretical: the demo/App-Directory-reviewer identity
(`8745115872`) has `expires_at = 2026-11-14` (absolute ceiling lifted, per
#410) but `last_used_at = 2026-08-16`, meaning the idle sweep will revoke it
around 2026-09-15 regardless. The only reason the demo account currently
survives is an out-of-band `labs-mctl-telegram-demo-session-refresh` CronJob
that keeps bumping `last_used_at`/`send_enabled` outside the application's own
TTL logic — a workaround the exemption was supposed to make unnecessary.

Reusing the `expires_at IS NULL` trick for `last_used_at` does not work:
`MarkLastUsed` (`internal/db/store.go`) stamps `last_used_at = now()` on
*every* successful tool dispatch (`Pool.Borrow`), so any single real call
would re-arm a NULL-turned-marker value back into a live timestamp. The
exemption for the idle branch has to be a real predicate — "is this
`telegram_user_id` on the exempt list" — evaluated independently of whatever
value happens to be sitting in `last_used_at`.

## User stories

- AS an operator running a long-lived service/demo Telegram identity on the
  exempt list, I WANT that identity to survive indefinitely regardless of how
  long it goes unused, SO THAT I never have to run an out-of-band job or an
  interactive reconnect to keep it alive.
- AS a platform maintainer, I WANT `CheckSessionValid`, `SweepIdleSessions`,
  and `ListIdentities` to agree on which sessions are alive, SO THAT the
  identities list, the request-time gate, and the background sweeper never
  contradict each other.
- AS a future maintainer reading `SESSION_TTL_EXEMPT_TG_IDS`, I WANT the name
  and its doc comment to mean "exempt from session TTL" (full stop), not
  "exempt from the absolute TTL only", SO THAT the config is not a trap.

## Acceptance criteria (EARS)

- WHEN `Store.SweepIdleSessions` runs AND a row's `telegram_user_id` is on the
  configured TTL-exempt list THE SYSTEM SHALL NOT revoke that row, regardless
  of how old `last_used_at` is.
- WHEN `Store.SweepIdleSessions` runs AND a row's `telegram_user_id` is NOT on
  the exempt list AND `last_used_at` is older than the idle TTL THE SYSTEM
  SHALL revoke that row, exactly as today.
- WHEN `Store.CheckSessionValid` evaluates a session belonging to an exempt
  `telegram_user_id` THE SYSTEM SHALL NOT reject it for idle expiry
  (`ReasonIdle`), regardless of how old `last_used_at` is.
- WHEN `Store.CheckSessionValid` evaluates a session belonging to a
  non-exempt `telegram_user_id` whose `last_used_at` is older than the idle
  TTL THE SYSTEM SHALL reject it with `ReasonIdle`, exactly as today.
- WHEN `Store.ListIdentities` computes `HasSession` for an exempt identity
  THE SYSTEM SHALL report it as having a session whenever it is non-revoked
  and finalised (`telegram_user_id IS NOT NULL`), independent of
  `last_used_at`, so the list keeps matching what `CheckSessionValid` would
  accept.
- WHILE an identity is NOT on `SessionTTLExemptTGIDs` THE SYSTEM SHALL
  continue to enforce both the idle and absolute TTL on it exactly as before
  this change (no behavior change for the non-exempt path).
- IF an identity is removed from `SESSION_TTL_EXEMPT_TG_IDS` THEN THE SYSTEM
  SHALL resume enforcing the idle TTL on it on the very next evaluation (no
  stored "was once exempt" state persists anywhere — the exemption is
  computed from the live config on every check, exactly like the absolute
  side already does via `s.ttlExempt`).
- WHEN the existing test `TestIdleTTLStillAppliesToExempt`
  (`internal/db/store_ttl_test.go`) is updated for this change THE SYSTEM
  SHALL have its assertion inverted (exempt identity survives the idle sweep)
  and renamed to reflect the new invariant, per the issue's own instruction
  that the old test "pins the current behavior and must be rewritten
  alongside this."
- WHEN a new test asserts the combined invariant THE SYSTEM SHALL prove both
  sides in one place: an exempt identity with a very old `last_used_at`
  survives `SweepIdleSessions`, and a non-exempt identity with the same
  `last_used_at` does not.

## Out of scope

- Removing the `labs-mctl-telegram-demo-session-refresh` CronJob or the
  `DEMO_REVIEWER_ENABLED` gate. The issue explicitly says not to do this yet:
  the CronJob also re-revokes an already-revoked row and force-resets
  `send_enabled=false`, neither of which this exemption performs. That
  behavior needs a deliberate follow-up decision (port it into the
  application or consciously drop it) and lives in the platform-gitops repo,
  not this one.
- Changing the exemption's storage/config mechanism (`SESSION_TTL_EXEMPT_TG_IDS`,
  `WithAbsoluteTTLExempt`, `ReconcileTTLExemptions`). Those stay as-is; this
  proposal only widens what the existing exempt set protects against.
- Any change to the absolute-TTL exemption path (`expires_at IS NULL`
  handling, `Migrate`'s backfill skip, `ReconcileTTLExemptions`). That
  machinery is correct and untouched by this issue.
- Renaming `SessionTTLExemptTGIDs` / `WithAbsoluteTTLExempt` / the env var.
  The env var name (`SESSION_TTL_EXEMPT_TG_IDS`) was already TTL-generic, only
  the implementation lagged; `WithAbsoluteTTLExempt`'s name is arguably now
  slightly stale (it exempts both TTLs going forward) but renaming a public
  `*Store` method is a larger, separate refactor and not required to fix the
  bug. Flagged under Open questions.

## Open questions

- Should `WithAbsoluteTTLExempt` be renamed (e.g. to `WithTTLExempt`) now
  that it drives both the absolute and idle exemption, or left as-is with an
  updated doc comment to avoid an unnecessary rename churn across
  `cmd/server/main.go` and the test suite? This proposal's most reasonable
  interpretation: keep the name, update the doc comment to state plainly that
  it now exempts both TTLs, and note the rename as a nice-to-have for a
  separate PR — renaming a constructor-chained method is pure churn with no
  behavior benefit and the issue itself does not ask for it.
- Should `ListIdentities`' idle-exempt handling reuse the exact SQL fragment
  as `SweepIdleSessions` (a `telegram_user_id IN (...)` list built from the
  same exempt set), or should it be expressed differently since it is a
  `SELECT`, not an `UPDATE`? This proposal's interpretation: reuse the same
  dynamic `IN (...)` fragment/args builder for both, since they must agree
  and the issue explicitly asks for `ListIdentities` to stay consistent with
  `CheckSessionValid`.
