# Basket canary: mctl-api environment, secret references, rollout markers (text only, not applied)

Part of the Glovo Basket MCP production canary (mctlhq/mctl-api#1006, plan
mctlhq/mctl-gitops#2457). Runbook: `docs/runbooks/glovo-basket-canary.md`
(steps B1 and B2). The target is
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, a reconciled
file under the leak guard (#2470), so the diffs below stay text until the
activation PRs. Names and defaults were read from mctl-api PR #1014 (head
`92cbd3d`, which contains #1007 and #1008): `cmd/api/glovo_basket.go`,
`cmd/api/glovo_basket_ui_options.go`, `cmd/api/glovo_team_grant.go`,
`cmd/api/main.go`.

## Everything the basket MCP needs, by name

All of these are read once at process start. Defaults are what the code does
when the name is unset. "Refuses boot" means `os.Exit(1)` with an
`invalid configuration` log line: on a rolling update the new pods never
become ready and the old pods keep serving (a stalled rollout, not an outage).

| Name | Value at activation | Default | Wrong or missing | Step |
| --- | --- | --- | --- | --- |
| `GLOVO_ENABLED` | `"true"` | unset = off | value other than empty/`true`/`false`: refuses boot. `true` without the items below: refuses boot | B1 |
| `GLOVO_MCP_RESOURCE` | `https://glovo.mctl.ai/mcp` | unset = no Glovo resource | `true` flags need it; must be `https://<host>/mcp` with no query or fragment | B1 |
| `GLOVO_BASKET_MCP_ENABLED` | `"true"` | unset/empty/`false` = mounts nothing | not a Go bool: refuses boot. `true` without `GLOVO_ENABLED`, its resolver, the Glovo pool, the work-items ledger, or with either schema not verifying: refuses boot | B1 |
| `GLOVO_BASKET_UI_ENABLED` | `"true"` | unset = page off, silently | any value but exactly `true` = off. `true` without `GLOVO_BASKET_MCP_ENABLED=true`: refuses boot. `true` with a missing page prerequisite: page stays off and one ERROR line names what is missing; `approval_url` is then not returned | B2 |
| `GLOVO_BASKET_UI_CLIENT_ID`, `GLOVO_BASKET_UI_CLIENT_SECRET` | references only, via chart slot `glovoBasketUISecret` | unset | both needed or the page stays off (logged) | B2 |
| `GLOVO_DB_URL` | `postgresql://$(GLOVO_DB_USER):$(GLOVO_DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/mctl-api?sslmode=require`, credentials from Secret `mctl-api-glovo-runtime-db` | unset | `GLOVO_ENABLED=true` without it: refuses boot (no `AUDIT_DB_URL` fallback) | staged in #2563 (A15) |
| `GLOVO_DB_RUNTIME_ROLE`, `GLOVO_DB_MIGRATION_ROLE` | `glovo_runtime`, `glovo_migrator` | unset | `GLOVO_ENABLED=true` without both: refuses boot | staged in #2563 (A15) |
| `GLOVO_NON_SELECTABLE_TENANTS` | leave unset | `admins` | empty counts as unset. `admins` can never be the chosen team; every other team is selectable by an allowlisted member | none |
| `OAUTH_DB_URL` | UNKNOWN, see Unknowns | falls back to `AUDIT_DB_URL` for the refresh store | `GLOVO_ENABLED=true` needs it set EXPLICITLY (`ExplicitOAuthDB`): refuses boot if only the fallback is in effect | B1 precondition |
| `TENANT_AUTHZ_MODE` | already `principal` in gitops | | anything else: `GLOVO_ENABLED=true` refuses boot, and the page stays off | none |
| `SELF_URL` | already `https://api.mctl.ai` | | the approval page origin and its `approval_url` origin come from it; the ZITADEL redirect is `<SELF_URL>/glovo/basket/approvals/callback` | none |
| `MCTL_OIDC_PROVIDERS`, `ZITADEL_LINK_PROVIDER` | already set through `oidcProvidersSecret`; provider `zitadel` | provider `zitadel` | the page needs an entry with that name, and `MCTL_FEDERATION_DISABLED` off | none |
| `WORK_ITEMS_DB_URL` | as decided by #2563/#2579 (legacy DSN preserved until the operator step) | falls back to `AUDIT_DB_URL` | the basket needs the work-items ledger non-nil. Which role it connects as must match the grants `ApplyGlovoApprovalSchema` issues, see runbook step D | D |

The allowlist is data, not env: `PUT
/api/v1/glovo/pilot/{tenant}/principals/{principal_id}` (human platform admin
only) adds a (team, principal) pair; `DELETE` removes it. It starts empty. An
empty allowlist means nobody can obtain a Glovo-audience token or use the MCP.

## References only, no values

- `GLOVO_BASKET_UI_CLIENT_ID` / `GLOVO_BASKET_UI_CLIENT_SECRET`: keys in
  Secret `mctl-api/mctl-api-oidc-zitadel`, written by the `zitadel-iac` Job
  from the ZITADEL client `mctl-api-glovo-basket` (staged in #2582). They reach
  the pod through a chart slot (`glovoBasketUISecret: mctl-api-oidc-zitadel`,
  optional `secretKeyRef`s like `devLoopDecideSecret`). The slot does not exist
  in the chart yet: it is a mctl-api chart change (prerequisite below).
  There is no Vault path and no ExternalSecret for it.
- `GLOVO_DB_*`: Secret `mctl-api-glovo-runtime-db` from the ExternalSecret
  staged in #2563 (`deploy/staged/glovo-m1/db/externalsecrets.yaml`), listed
  in `envFromOptionalSecrets`. Not repeated here.
- No new ExternalSecret, Vault policy or Secret is needed by the basket MCP.

## Must stay unset (each would switch on something outside the canary)

`GLOVO_JOIN_ENABLED`, `MCTL_GLOVO_CONTROL_ENABLED`, `MCTL_BRIDGE_ENABLED`,
`COMMERCE_DB_URL`, `MCTL_GLOVO_FACADE_TOKEN`, `MCTL_GLOVO_WORKER_TOKEN_FILE`,
`MCTL_GLOVO_CONTROL_WORKER`, `GLOVO_SYNTHETIC_HANDOFF_BASE_URL`. With
`GLOVO_ENABLED=true` and no worker token the synthetic connection routes
(`/api/v1/glovo/facade/*`, `/glovo/worker/*`) are mounted on the main host
behind a feature gate that answers 503 `not_ready` (`WorkerConfigured` is
false); that is a side effect of the shared `GLOVO_ENABLED` switch, to be
confirmed in step B1 (runbook), not something the basket uses.

## Prerequisite, mctl-api chart

`glovoBasketUISecret` slot in `helm/values.yaml` and `helm/templates/
deployment.yaml`, mirroring `devLoopDecideSecret` (lines 58-70 and 242-250 of
the chart at mctl-api `main`): two optional `secretKeyRef`s
(`GLOVO_BASKET_UI_CLIENT_ID`, `GLOVO_BASKET_UI_CLIENT_SECRET`), a `fail` when
the same name is also given in `env`, and a render test. #1007 has no slot
(its description of the activation order says so). Ships with the release
that carries the Basket code; until the slot exists, B2 cannot be applied.

## ROLLOUT_MARKER: which steps need a bump

The Deployment pod template changes whenever `env`, `envFromOptionalSecrets`
or a `secretKeyRef` slot changes, so Argo rolls the pods on its own. The
marker is still bumped in every step below because it is the repository's
audit trail for "why were the pods restarted" and covers the one case a spec
change does not: a Secret that exists already and changes content (rotation,
or the `zitadel-iac` Job adding the two client keys after the pods started).

| Change | Pods roll without the marker? | Marker bump |
| --- | --- | --- |
| B1: `GLOVO_ENABLED`, `GLOVO_MCP_RESOURCE`, `GLOVO_BASKET_MCP_ENABLED` | yes (env changed) | bump, recommended |
| B2: slot + `GLOVO_BASKET_UI_ENABLED` | yes (env and `secretKeyRef` changed) | bump, REQUIRED in the sense that the `zitadel-iac` apply with the two keys must precede it; bump only after that apply (see the marker comment in the file) |
| Rotating the ZITADEL client secret, or a `mctl-api-glovo-runtime-db` sync | no | REQUIRED, alone, after the Secret changed |
| Kill switch, flags off | yes | bump, recommended |
| Ingress host add or remove | no pod change at all | not needed |

## Diff B1: basket MCP on, approval page off

`git apply --check` was clean against main at the time of staging
(9c87fe961). Extract the fenced diff.

```diff
diff --git a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
index eace5f3d9..45ea58587 100644
--- a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
+++ b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
@@ -63,10 +63,10 @@ spec:
             # start, so when a rollout depends on generated configuration
             # (for example zitadel-iac output), bump only after it is applied.
             # The line below records why the current value was set.
-            # This rollout loads OAUTH_JWT_SIGNING_KEYS, which #2171 mapped
-            # into mctl-api-secrets (step C0 of mctlhq/mctl-api#805); envFrom
-            # is read only at container start.
-            ROLLOUT_MARKER: "2026-10-26-jwt-signing-keys"
+            # This rollout turns the Glovo basket MCP on (mctl-api#1006, step
+            # B1 of docs/runbooks/glovo-basket-canary.md): the glovo store
+            # and the basket schemas are read once at start.
+            ROLLOUT_MARKER: "2026-MM-DD-glovo-basket-b1"
             ARGOCD_URL: https://ops.mctl.ai
             # Repositories the orchestrator DevLoop principal may start or
             # read a DevLoop for (mctlhq/mctl-api#963), exact and
@@ -366,6 +366,17 @@ spec:
             # (envFromExtraSecret below). Without both the endpoint answers
             # 401/503 and nothing is published.
             EVENTS_VALKEY_URL: "redis://github-producer@valkey.platform-events.svc.cluster.local:6379/0"
+            # Glovo basket MCP canary (mctlhq/mctl-api#1006). Fail-closed
+            # chain: GLOVO_BASKET_MCP_ENABLED needs GLOVO_ENABLED, which
+            # needs the resource, the Glovo database (GLOVO_DB_* above, from
+            # the A15 staging) and an explicit OAUTH_DB_URL; anything missing
+            # refuses the boot, never a half-on feature. "true"/"false" only.
+            # The allowlist is not env: it stays empty until an admin PUTs
+            # /api/v1/glovo/pilot/{tenant}/principals/{principal_id}.
+            # Kill switch: remove the Ingress host first, then these lines.
+            GLOVO_ENABLED: "true"
+            GLOVO_MCP_RESOURCE: https://glovo.mctl.ai/mcp
+            GLOVO_BASKET_MCP_ENABLED: "true"
             # ARGO_WEBHOOK_SECRET is not listed here; envFromSecret below
             # injects it from Vault platform/mctl-api/argo-webhook (SOC F13).
 
```

## Diff B2: approval page on (applies on top of B1)

Precondition: the `zitadel-iac` change of #2582 is applied and the Secret has
the two keys (read-only check is by effect, not by reading the Secret: the
page logs `glovo basket approval page enabled` on start, or one ERROR naming
what is missing). Also needs the chart slot above, released.

```diff
diff --git a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
index 45ea58587..fdb675ea1 100644
--- a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
+++ b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
@@ -63,10 +63,11 @@ spec:
             # start, so when a rollout depends on generated configuration
             # (for example zitadel-iac output), bump only after it is applied.
             # The line below records why the current value was set.
-            # This rollout turns the Glovo basket MCP on (mctl-api#1006, step
-            # B1 of docs/runbooks/glovo-basket-canary.md): the glovo store
-            # and the basket schemas are read once at start.
-            ROLLOUT_MARKER: "2026-MM-DD-glovo-basket-b1"
+            # This rollout turns the Glovo basket approval page on
+            # (mctl-api#1006, step B2 of docs/runbooks/glovo-basket-canary.md):
+            # GLOVO_BASKET_UI_CLIENT_ID/SECRET come from mctl-api-oidc-zitadel
+            # and are read only at container start.
+            ROLLOUT_MARKER: "2026-MM-DD-glovo-basket-b2"
             ARGOCD_URL: https://ops.mctl.ai
             # Repositories the orchestrator DevLoop principal may start or
             # read a DevLoop for (mctlhq/mctl-api#963), exact and
@@ -377,6 +378,11 @@ spec:
             GLOVO_ENABLED: "true"
             GLOVO_MCP_RESOURCE: https://glovo.mctl.ai/mcp
             GLOVO_BASKET_MCP_ENABLED: "true"
+            # The owner approval page (mctl-api#1007). Needs the chart slot
+            # glovoBasketUISecret below and the ZITADEL client; without them
+            # the page stays off and approval_url is not returned. Requires
+            # GLOVO_BASKET_MCP_ENABLED (else the boot is refused).
+            GLOVO_BASKET_UI_ENABLED: "true"
             # ARGO_WEBHOOK_SECRET is not listed here; envFromSecret below
             # injects it from Vault platform/mctl-api/argo-webhook (SOC F13).
 
@@ -477,6 +483,15 @@ spec:
           # that one does need the keys: mctl-api refuses to start in those
           # modes without them. Rollback: delete this line.
           oauthZitadelSecret: mctl-api-oidc-zitadel
+
+          # GLOVO_BASKET_UI_CLIENT_ID / GLOVO_BASKET_UI_CLIENT_SECRET for the
+          # Glovo basket approval page (mctlhq/mctl-api#1007): the
+          # confidential `mctl-api-glovo-basket` client that zitadel-iac
+          # writes into the same Secret (mctl-gitops#2582). Optional refs, so
+          # a Secret without the keys leaves the page off. Needs the chart
+          # slot of the same name (mctl-api chart change). Rollback: delete
+          # this line and GLOVO_BASKET_UI_ENABLED.
+          glovoBasketUISecret: mctl-api-oidc-zitadel
           {{- if .Values.usageWriter.enabled }}
 
           # The usage-writer token (mctlhq/.github#50), from the
```

## Kill switch and rollback

- Ingress first: revert the Ingress diff (`ingress.patch.md`). Traffic stops
  at Traefik within about a minute.
- Revoke access without a deploy: `DELETE
  /api/v1/glovo/pilot/{tenant}/principals/{principal_id}` (admin). The next
  MCP call of that principal is refused (per-request scope re-check), and its
  Glovo team grant stops resolving. Also instant, and reversible with `PUT`.
- Flags: revert B2 then B1, one PR each, or both at once. Order inside the
  rollback does not matter once the host is unrouted. A boot with
  `GLOVO_BASKET_UI_ENABLED` removed and the MCP still on is valid; the reverse
  (UI on, MCP off) refuses the boot, so never remove `GLOVO_BASKET_MCP_ENABLED`
  alone.
- Data stays: the basket tables are insert-only by design and are not dropped
  by a rollback. Pending approvals expire on their own TTL.

## Unknowns (not determinable from this repository, read-only)

1. Whether `OAUTH_DB_URL` is set explicitly in production. It is not in the
   public gitops env; it could come from `mctl-api-secrets`. Secret data and
   key names are not read by agents. If it is not set, B1 refuses the boot.
   Remedy if it is not: an explicit `OAUTH_DB_URL` equal to `AUDIT_DB_URL`
   (same database, same behaviour, now explicit), decided by the operator.
2. Whether any other source (`mctl-api-secrets`, `mctl-api-events`,
   `mctl-api-zitadel-hook`, `mctl-api-orchestrator-devloop`) already supplies a
   `GLOVO_*` name. A stray malformed value would refuse the boot (the same
   concern as #2529 gate G4(b)). Operator names-only check, per #2529.
3. Which team (tenant) the owner uses for the canary and whether the owner
   already holds `developer` on it (the decision handler requires live
   `developer` membership of the basket's team).
