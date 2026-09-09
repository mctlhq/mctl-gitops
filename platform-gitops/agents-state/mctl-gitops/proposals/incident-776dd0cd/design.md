# Design: incident-776dd0cd

## Confidence: LOW

## Diagnosis
MctlTelegramSessionBorrowSlowBurn is a multi-window burn-rate alert on the
labs tenant's mctl-telegram Telegram session-borrow-latency SLO; it fired at
6x the allowed burn rate sustained over a 6h window. mctl-agent's escalation
record confirms no skill matched this alert (type=generic, unrecognized
alert name), so nothing was auto-diagnosed. The base-service log window
fetched for this incident shows no ERROR or WARN lines and every canary probe
and MCP tool call completing with status "ok" in ~1-1.4s. The one notable
pattern is a sustained stream of MCP OAuth dynamic client_registration
requests (roughly one every 1-2 seconds) from the same client_name
(`cmg0c9xxt020wec596hjg563i`), consistent with a client stuck retrying
registration rather than registering once. Sustained retry traffic on the
same request-handling path used to borrow Telegram MTProto sessions from the
pool is a plausible contributor to elevated (but not failing) borrow latency,
but the fetched logs do not expose session-pool internals (queue depth, wait
time, pool size), so this link is inferred, not directly observed. Because
the causal chain is not confirmed, this proposal is marked LOW confidence.

## Proposed Fix
As a minimal, safe, config-only mitigation (no application code change),
increase headroom on the labs mctl-telegram base-service so that session
borrowing has more CPU/concurrency slack to absorb the registration retry
traffic while the retry loop itself is investigated separately:

- File: `platform-gitops/services/labs/mctl-telegram/values.yaml` (or the
  team/service values file used for the labs mctl-telegram base-service in
  this repo — implementer should locate the exact path via the existing
  `image.tag: 0.62.1`, `host: tg.mctl.ai` config for this service).
- Field: `resources.requests.cpu` / `resources.limits.cpu`
- Current value: whatever is currently set (verify before editing).
- New value: increase by roughly 30-50% over current request/limit (e.g.
  `250m` -> `350m` request, proportional limit bump), unless the current
  values already look generous, in which case skip the resource bump and
  only enable autoscaling below.
- Optionally also enable/raise `autoscaling.minReplicas` by one if HPA is
  already configured for this service, to add a second replica for borrow
  concurrency headroom.

## Scope
Minimal. Only touch the labs mctl-telegram base-service resource/autoscaling
fields in its Helm values. Do not touch AlertManager rule thresholds (the
alert appears to be correctly firing on a real, if not fully explained,
symptom) and do not attempt an application-level rate limit on OAuth dynamic
client registration here — that would require a Go/Python code change in the
mctl-telegram service repo itself, which is out of scope for a gitops-only
fix. If the resource bump does not resolve the slow burn, the follow-up is a
code-level investigation of the client_registration retry loop in the
mctl-telegram repo.
