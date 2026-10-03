# Investigate live host `mctl.ru` vs. documented primary host `mctl.ai`

## Context
`mctl_get_service_config` for `mctl-web`/`admins` reports the live host as `mctl.ru`.
`context/architecture.md`, however, documents `mctl.ai` as the primary host — serving
the landing page, docs, privacy policy, GitHub OAuth callbacks, and Backstage-integrated
tenant-creation forms — with `mctl.ru` (along with `mctl.me`) listed only as a
redirect-source domain that the Cloudflare Worker forwards to `mctl.ai`.

This discrepancy is currently **unconfirmed**: it may simply be a stale or mislabeled
field in the mctl config-tool output (e.g. a leftover default, a display bug, or a
config key that was never updated after a domain migration) rather than an actual
production routing problem. It is equally possible that production traffic really is
being served from `mctl.ru` in a way that diverges from the documented architecture,
which would be a meaningful concern: GitHub OAuth callback allow-lists, session
cookies, and CORS rules are typically scoped to a specific host, and a genuine mismatch
here could cause silent auth or cross-origin failures, or — worse — expose an
unintended attack surface if `mctl.ru` accepts requests that should only be valid on
`mctl.ai`. This proposal treats the finding strictly as **investigate first, then fix
only if confirmed** — it does not assume the worst-case interpretation is true.

This proposal owns only the host/domain portion of the discrepancy. The related
version-number drift (imageTag `7.5.3` vs. `current-version.md`'s `4.6.2`) found in the
same `mctl_get_service_config`/`mctl_get_service_status` output is explicitly out of
scope here and is owned by `proposals/reconcile-current-version-doc/`.

## User stories
- AS a service owner I WANT to know with certainty whether `mctl-web` in `admins` is
  actually serving live traffic from `mctl.ru`, or whether the config tool is reporting
  a stale/mislabeled value, SO THAT I can decide whether any routing, OAuth, or CORS
  change is actually necessary.
- AS a security engineer I WANT confirmation of which host(s) GitHub OAuth callbacks,
  session cookies, and CORS policy are actually scoped to in production SO THAT I can
  detect and close any silent mismatch between documented and live configuration.
- AS a future researcher/analyst agent I WANT this discrepancy tracked to a documented
  root cause (not left as a raw, unexplained flag) SO THAT it does not get re-surfaced
  and re-investigated from scratch in a future daily cycle.

## Acceptance criteria (EARS)
- WHEN this investigation is performed THE SYSTEM SHALL determine, with evidence (e.g.
  direct inspection of the Cloudflare Worker route bindings, DNS records, and/or
  `mctl_get_service_config`'s underlying data source), whether `mctl.ru` is genuinely
  serving live application traffic or is a stale/mislabeled config-tool value.
- IF the investigation confirms `mctl.ru` is only a stale/mislabeled config-tool field
  (i.e. production traffic is genuinely served from `mctl.ai` as documented) THEN THE
  SYSTEM SHALL correct the config-tool's host label/source data (or file a ticket
  against the mctl config tool itself) and make NO changes to Worker routes, OAuth
  allow-lists, or CORS policy.
- IF the investigation confirms `mctl.ru` is genuinely receiving and serving
  non-redirect application traffic (i.e. a real routing divergence from the documented
  redirect-only behavior) THEN THE SYSTEM SHALL produce a follow-up fix plan covering
  Worker route configuration, GitHub OAuth callback allow-list entries, and CORS policy
  before any code or config change is merged.
- WHILE the root cause is unconfirmed THE SYSTEM SHALL NOT make any change to Cloudflare
  Worker redirect rules, GitHub OAuth allow-lists, or CORS configuration.
- WHEN the investigation concludes THE SYSTEM SHALL document the confirmed root cause
  and outcome in this proposal (or a linked follow-up), so the finding is not
  re-flagged as an open question in a future inbox cycle.

## Out of scope
- The version-number drift (imageTag `7.5.3` vs. `current-version.md`'s `4.6.2`) found
  in the same tooling output — owned by `proposals/reconcile-current-version-doc/`.
- Any actual change to Worker redirect rules, OAuth allow-lists, or CORS policy, unless
  and until the investigation confirms a genuine routing divergence (see acceptance
  criteria above) — this proposal's primary deliverable is the investigation itself,
  not a pre-committed fix.
- Broader domain/DNS strategy review beyond confirming the specific `mctl.ru` vs.
  `mctl.ai` discrepancy reported by `mctl_get_service_config`.
