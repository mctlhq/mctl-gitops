# Design: incident-a436160e

## Confidence: LOW

## Diagnosis
`mctl-agent` escalated this ticket because it is a generic alert with no
matching skill — it collected evidence but performed no diagnosis. The
`labs-mctl-telegram` base-service logs show a `bridge: authentication
failed` / `err="JWT expired"` line recurring roughly once per minute,
continuously across the fetched 6h window, which lines up with the alert's
own "session borrow slow burn (6x, 6h)" description: something is
repeatedly trying to borrow a session and repeatedly failing bridge
authentication on an expired JWT.

`platform-gitops/services/labs/mctl-telegram/values.yaml` contains a Job,
`labs-mctl-telegram-local-mode-flip-1`, whose own comments describe it as a
**one-shot** change that flipped `telegram_accounts.mode` to `'local'` for
Telegram user `8745115872` (the App-Directory demo/reviewer identity) "to
prove the routing" works. Local Bridge mode routes that account's session
traffic through a bridge daemon that authenticates with a JWT; the comments
explicitly note that account is safe to leave in local mode only "because
`DEMO_REVIEWER_ENABLED` is false, so both demo CronJobs are pruned and
nothing automated runs against it" — but they do not address the
base-service's own periodic session-borrow/health-check path, which this
evidence suggests continues to try to use the bridge for that account
regardless of the demo-reviewer flag. With no bridge daemon actively
authenticating for `8745115872` (the one-shot experiment already ran; the
account is not in ongoing local-bridge use), each borrow attempt against
that session fails with an expired JWT — matching both the log pattern and
the alert's slow-burn shape.

The comments on the flip Job themselves anticipate this: "If another
App-Directory review is scheduled, run the restore Job first — the hosted
session is not destroyed by this, only left unused." No such restore Job
exists yet in this file or elsewhere in
`platform-gitops/services/labs/mctl-telegram/`. This proposal is that
restore Job.

This diagnosis is marked LOW confidence because:
- The incident record's own `service` field was empty; service identity was
  inferred from the alert name and the summary text, not from a field
  mctl-agent populated itself.
- The correlation between the `bridge: authentication failed` log line and
  telegram_accounts row `8745115872` specifically (as opposed to some other
  account or a different bridge client) is inferred from the gitops history
  and comments, not from a log line that names the account id directly.
- No direct read of `telegram_accounts.mode` for this account was possible
  from this responder (no DB access, no shell) to confirm it is still
  `'local'` rather than already reverted by some other means.

## Proposed Fix
Add a one-shot restore Job to
`platform-gitops/services/labs/mctl-telegram/values.yaml`, `extraObjects`,
mirroring `labs-mctl-telegram-local-mode-flip-1` but reverting the change:
set `telegram_accounts.mode = 'hosted'` (instead of `'local'`) for the row
where `user_id` resolves from `telegram_login_id = '8745115872'` and
`revoked_at IS NULL`, using the same `RETURNING id` / empty-result failure
pattern as the existing flip Job so a no-op UPDATE surfaces as a failed Job
rather than a silent no-op. Name it
`labs-mctl-telegram-local-mode-restore-1` so it coexists with (rather than
replaces) the existing flip Job, preserving that Job's history.

This does not touch `send_enabled`, `revoked_at`, or any other column, and
does not change `DEMO_REVIEWER_ENABLED` or any env var — only the one
`mode` field the flip Job itself changed.

If verification during implementation shows the account is not actually
still in `'local'` mode (e.g. it was already reverted through some other
path), the implementer should downgrade this to a no-op / close without
merging rather than force the UPDATE.

## Scope
Minimal. One new one-shot `batch/v1` Job in the existing `extraObjects`
list of `platform-gitops/services/labs/mctl-telegram/values.yaml`. No image,
resource, or env var changes.
