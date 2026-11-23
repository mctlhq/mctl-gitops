# Design: issue-2567-fix-glovo-canary-reconcile-staged-gitops

## Current state

The inert P0 package lives at `deploy/staged/glovo-m1/` (added by #2470). The README states that no
ApplicationSet, Application or `manifest-generate-paths` matches `deploy/`. CI job `glovo-m1` in
`.github/workflows/validate-manifests.yml` (around line 1124) runs
`scripts/validate-glovo-m1-staging.py --selftest` and then the default mode. The validator has two
halves: `check_staged_values`/`check_provenance` (pure YAML checks), `leak_guard` (deny-only, no
`glovo|mctl-assistants` in `platform-gitops/**` outside `agents-state/`), and `render_checks`
(`helm template` of `platform-gitops/helm-charts/base-service` and `.../tenant` plus `kubeconform
-strict` on the renders and on `netpol/*.yaml`).

Files and what they say today (repo HEAD `628471c`):

| File | Current content relevant to drift |
| --- | --- |
| `facade/values.yaml` | image `ghcr.io/mctlhq/glovo-mcp-facade:0.0.0`; env `OAUTH_ISSUER_URL`, `OAUTH_RESOURCE`, `GLOVO_ENABLED`, `GLOVO_ALLOWLIST`, `GLOVO_TEAM_FALLBACK: "false"`, with a comment that the key names are placeholders; no credential file mount; ingress off, host `glovo.mctl.ai`, path `/mcp`, extra ingress `/.well-known/oauth-protected-resource` |
| `provider-worker/values.yaml` | image `ghcr.io/mctlhq/glovo-provider-worker:0.0.0`; `TEMPORAL_NAMESPACE: mctl-assistants-provider-glovo`; ExternalSecret `glovo-provider-temporal` to `TEMPORAL_CLIENT_CREDENTIAL` |
| `control-worker/values.yaml` | image `ghcr.io/mctlhq/glovo-control-worker:0.0.0`; `TEMPORAL_NAMESPACE: mctl-assistants`; ExternalSecret `glovo-control-temporal` |
| `provider-tenant/values.yaml` | tenant `mctl-assistants-provider-glovo`, `allowClusterEgress: false`, `allowInternetEgress: false` |
| `netpol/facade-to-control.yaml` | ingress into `admins` control worker **from** the `labs` facade on 8080 |
| `netpol/worker-to-temporal.yaml` | provider egress to DNS and `temporal:7233` |
| `compatibility.yaml` | `envKeys` include `GLOVO_TEAM_FALLBACK`, `OAUTH_ISSUER_URL`, `OAUTH_RESOURCE` |
| `budgets.yaml` | `killSwitch.keys` include `GLOVO_TEAM_FALLBACK` |
| `secrets-map.md` | provider Temporal credential row; facade "none in P0" |
| `temporal-namespaces.patch.md` | adds `mctl-assistants` and `mctl-assistants-provider-glovo` |
| `provenance.yaml` | three images, all `<digest-pending>`; no `deployable` flag |
| `target-paths.yaml` | lists both netpols with target "decided in P1" |
| `CROSSWALK.md` | pinned to G `f9640935`, A `a9ca5814`, T `27c671d2`; M14-M16 name the drift but say "P1 prep PR" |
| `README.md` | "Obsolete staged artifacts" section lists the same drift |

Canonical sources read in this clone (agents-state proposals):

- mctl-telegram#1235 (`status: merged`), `design.md:111-135`: frozen image
  `ghcr.io/mctlhq/mctl-glovo-mcp`, component `labs/glovo-mcp`, routes including
  `/.well-known/oauth-protected-resource/mcp`, config `GLOVO_MCP_ENABLED` (default false),
  `GLOVO_MCP_PUBLIC_BASE_URL`, `GLOVO_MCP_RESOURCE`, `GLOVO_MCP_ISSUER`, `GLOVO_MCP_JWKS_URL`,
  `GLOVO_MCP_AUTHORIZATION_SERVER`, `GLOVO_MCP_API_BASE_URL`, `GLOVO_MCP_API_CREDENTIAL_FILE`,
  `GLOVO_MCP_RATE_PER_MIN`, `GLOVO_MCP_METRICS_ALLOW_CIDR`; "No env names a tenant"; no
  `go.temporal.io` in the facade binary.
- mctl-telegram#1262 (`status: merged`), `design.md:180-195`: provider config `MCTL_API_BASE_URL`,
  `MCTL_BRIDGE_CREDENTIAL_FILE` (file only), `BRIDGE_WORKER_IDENTITY` (default `provider:glovo`),
  `BRIDGE_CLAIM_MAX`, `BRIDGE_POLL_INTERVAL`; the worker refuses to start if any `TEMPORAL_*` is set;
  origin-pinned transport, paths limited to `/api/v1/bridge/commands/`; `FAKE_ONLY=true` baked into
  `Dockerfile.glovo-provider-worker`; health and metrics on `:8081`; egress "only to the mctl-api
  origin" (`design.md:339`). No registry image name observed.
- mctl-agents#1044 (`status: proposed`), `design.md:387-426` and `requirements.md:187-190`:
  `TEMPORAL_NAMESPACE` must equal `mctl-assistants`; image publishing open
  (`ghcr.io/mctlhq/mctl-agents-assistants-control` proposed, build-only default).
- mctl-api#957 (`status: proposed`), `design.md:798-830`, `tasks.md:36` (A15): `GLOVO_DB_URL` and
  `WORK_ITEMS_DB_URL` explicit, no `AUDIT_DB_URL` fallback; `COMMERCE_DB_URL` is the commerce
  ledger's, not a Glovo pool; roles `glovo_runtime` (R1) and `glovo_migrator` (R2, credentials never in
  runtime or agents); flags `GLOVO_ENABLED`, `GLOVO_JOIN_ENABLED`, `GLOVO_CONTROL_START_ENABLED`
  (mctl-api side, all default off).
- PR #2563 (OPEN, head `6464978`): adds `deploy/staged/glovo-m1/db/{externalsecrets.yaml,
  migration-job.yaml, roles.patch.md, mctl-api-env.patch.md}` and a README change. This proposal does
  not touch those paths.

Note that `scripts/validate-glovo-m1-staging.py` currently **enforces** drift: it requires
`GLOVO_TEAM_FALLBACK == "false"`, the provider `TEMPORAL_NAMESPACE`, and a provider ExternalSecret,
and the selftest case "T4 team fallback on" exists. Fixing the manifests without changing the
validator turns CI red, which is why the validator and manifests change together.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/` listing: no `glovo-mcp` directory; `grep -rli glovo` over
  `$MCTL_GITOPS_ROOT/services` and `$MCTL_GITOPS_ROOT/tenants` returned nothing. No Glovo workload is
  in a reconciled path.
- `$MCTL_GITOPS_ROOT/tenants/`: `admins commerce-proof erpact karabu labs mctl namax66`; no
  `mctl-assistants-provider-glovo` tenant.
- `mctl_get_service_status(admins, mctl-api)`: Argo app `admins-mctl-api` Healthy/Synced; `service`
  is null (not a catalogue service), so the mctl-api values and port were not observed.
- mctl-api pod namespace/label from the clone: namespace `mctl-api`
  (`platform-gitops/argo-workflows/config/networkpolicy.yaml:37`), label
  `app.kubernetes.io/name: mctl-api` (`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-monitor.yaml:11`).
- `gh pr view 2563`: OPEN, files listed above.
- Not observed: live Temporal namespaces (CROSSWALK already marks NOT_OBSERVED), mctl-api container
  port, any built image or digest for the three components. These are UNKNOWN, not absent.

## Proposed solution

One staged-only PR on a feature branch touching only `deploy/staged/glovo-m1/**` (excluding
`db/`), `scripts/validate-glovo-m1-staging.py`, and `docs/runbooks/glovo-m1.md`. Order inside the PR:
tests first (commit 1 makes CI fail on the current tree), then fixes (commit 2 makes it pass).

### Drift findings and corrections

| ID | File | Staged value | Corrected value | Canonical source | Owner |
| --- | --- | --- | --- | --- | --- |
| D1 | `facade/values.yaml` image | `ghcr.io/mctlhq/glovo-mcp-facade` | `ghcr.io/mctlhq/mctl-glovo-mcp`, tag `0.0.0` | tg#1235 `design.md:113` | this PR |
| D2 | `facade/values.yaml` env | `OAUTH_ISSUER_URL`, `OAUTH_RESOURCE`, `GLOVO_ENABLED`, `GLOVO_ALLOWLIST`, `GLOVO_TEAM_FALLBACK` | `GLOVO_MCP_ENABLED: "false"`, `GLOVO_MCP_PUBLIC_BASE_URL: https://glovo.mctl.ai`, `GLOVO_MCP_RESOURCE: https://glovo.mctl.ai/mcp`, `GLOVO_MCP_ISSUER: https://api.mctl.ai`, `GLOVO_MCP_JWKS_URL` (UNKNOWN exact path), `GLOVO_MCP_API_BASE_URL`, `GLOVO_MCP_API_CREDENTIAL_FILE: /var/run/glovo/mctl-api-credential` | tg#1235 `design.md:125-135` | this PR; allowlist lives in mctl-api (#960), not facade env |
| D3 | `facade/values.yaml` | no credential mount | plan-only ExternalSecret `glovo-mcp-api-credential` (Vault `teams/labs/glovo-mcp/mctl-api-credential`, UNKNOWN until #2506/#2540) mounted as a file, never `envFrom` | tg#1235 `design.md:134`; README C4 | this PR (name only) |
| D4 | `facade` metadata route | `/.well-known/oauth-protected-resource` Prefix | unchanged; validator asserts Prefix covers `/.well-known/oauth-protected-resource/mcp` | tg#1235 `design.md:117` | this PR (test only) |
| D5 | `compatibility.yaml`, `budgets.yaml` | `GLOVO_TEAM_FALLBACK` and old key names | per-component `envKeys` (facade: D2 keys; provider: #1262 keys; control: `TEMPORAL_NAMESPACE`); `killSwitch` split: facade `GLOVO_MCP_ENABLED`, mctl-api `GLOVO_ENABLED`/`GLOVO_JOIN_ENABLED`/`GLOVO_CONTROL_START_ENABLED`/`MCTL_BRIDGE_ENABLED` (plan-only reference to #2563 env patch), `ingress.enabled` | #957, CROSSWALK C2/M14 | this PR |
| D6 | `provider-worker/values.yaml` | `TEMPORAL_NAMESPACE`, `glovo-provider-temporal` ExternalSecret | env `MCTL_API_BASE_URL` (UNKNOWN origin, see open questions), `MCTL_BRIDGE_CREDENTIAL_FILE: /var/run/bridge/credential`, `BRIDGE_WORKER_IDENTITY: provider:glovo`, `FAKE_ONLY: "true"`; ExternalSecret `glovo-provider-bridge` (Vault `teams/mctl-assistants-provider-glovo/provider-worker/bridge`, plan-only) mounted as file; probes on `:8081` | tg#1262 `design.md:67,183-195` | this PR |
| D7 | `netpol/worker-to-temporal.yaml` | egress to `temporal:7233` | removed; new `netpol/provider-egress-bridge.yaml`: default-deny egress, allow DNS and namespace `mctl-api` / `app.kubernetes.io/name: mctl-api` only | tg#1262 `design.md:339`; CROSSWALK M15 | this PR |
| D8 | `netpol/facade-to-control.yaml` | facade allowed into control worker | removed; new `netpol/control-ingress-deny.yaml` (empty ingress) and `netpol/control-egress.yaml` (DNS, `temporal:7233`, mctl-api) | CROSSWALK section 1 (control talks to Temporal + mctl-api only) | this PR |
| D9 | none | no facade egress policy | new `netpol/facade-egress.yaml`: DNS and mctl-api only; no `temporal`, no `admins` peer | tg#1235 (facade calls only mctl-api) | this PR |
| D10 | `control-worker/values.yaml` image | `ghcr.io/mctlhq/glovo-control-worker` | `ghcr.io/mctlhq/mctl-agents-assistants-control` (UNKNOWN until #1044 decides) | #1044 `requirements.md:187` | #1044 owner |
| D11 | `provenance.yaml` | no deployability marker | add `deployable: false` and `nameStatus: frozen|unknown` per image; validator refuses `deployable: true` while digest/commit pending | issue "no placeholder masquerading as deployable" | this PR |
| D12 | `temporal-namespaces.patch.md`, `secrets-map.md` | provider namespace and Temporal credential | provider namespace dropped; control namespace kept; secrets map lists facade/provider bridge credentials as files, control Temporal credential, and points to #2563 for `glovo_runtime`/`glovo_migrator` (migrator never in runtime or worker pods) | CROSSWALK M15, #957 R2 | this PR |
| D13 | `target-paths.yaml` | old netpol names | new netpol files listed with phase `p1`, target "decided in P1" | validator rule | this PR |
| D14 | `README.md` | "Obsolete staged artifacts" section | replaced by "Reconciled in #2567" pointer to CROSSWALK v2 | n/a | this PR |

`GLOVO_DB_URL`, `WORK_ITEMS_DB_URL`, `COMMERCE_DB_URL`, `GLOVO_JOIN_ENABLED` are mctl-api env, not
staged-component env. They are owned by #2563 (`db/mctl-api-env.patch.md`). This PR adds a validator
check that none of the facade/provider/control values carries any `*_DB_URL` key (runtime workers
never hold DB credentials) and records the #2563 names in the crosswalk; it does not create or edit
`db/`.

### Validator changes (`scripts/validate-glovo-m1-staging.py`)

- Remove the `GLOVO_TEAM_FALLBACK == "false"` and provider `TEMPORAL_NAMESPACE`/ExternalSecret
  requirements; replace the "T4 team fallback on" selftest with "fallback key present".
- New constants: `FACADE_IMAGE = "ghcr.io/mctlhq/mctl-glovo-mcp"`, `FACADE_ENV_ALLOWED` (#1235 keys),
  `PROVIDER_ENV_ALLOWED` (#1262 keys plus `APP_ENV`, `FAKE_ONLY`), `FORBIDDEN_ENV = re.compile(r"FALLBACK|_DB_URL$|^GLOVO_.*(TOKEN|SESSION|COOKIE|PASSWORD)|^GLOVO_API_|^GLOVO_BASE_URL$")`.
- New checks (each one `_need`, each with a selftest case that mutates the fixed tree back to the
  pre-fix value): D1 facade image; D2 facade env subset and `GLOVO_MCP_ENABLED == "false"`; D5 no
  forbidden key in any values/compatibility/budgets file; D6 provider has no `TEMPORAL_*` key, no
  `envFrom` secret containing Temporal, required bridge keys, identity regex, credential via volume
  not env; D7/D8/D9 NetworkPolicy semantics via a small `_peers(policy)` helper: provider and facade
  egress peers ⊆ {kube-system DNS, `mctl-api`}, control egress ⊆ {DNS, `temporal`:7233,
  `mctl-api`}, control ingress is empty, no policy anywhere admits facade → control or facade/provider
  → `temporal`; D11 `deployable: false` while any pending marker; every `*/values.yaml` has no
  credential value under `env`.
- A new selftest group "pre-fix tree" that copies the facade/provider/compatibility/netpol files as
  they are at `628471c` (embedded as fixture strings under `scripts/fixtures/glovo-m1-prefix/`) and
  asserts exit 6. That is the "fails before fix" evidence without relying on git history in CI.
- `render_checks` gains: `helm template` of each values file must render no `Ingress` for provider and
  control, the facade render with `ingress.enabled=true` must produce exactly hosts `[glovo.mctl.ai]`
  and paths `/mcp` and the metadata prefix, and every rendered `Deployment` container must have no env
  whose name matches `FORBIDDEN_ENV`. kubeconform runs on every file under `netpol/`.
- `leak_guard` unchanged, except that its image list now includes the corrected names (read from
  `provenance.yaml`, so automatic).

### CROSSWALK v2

`CROSSWALK.md` gains `Version: v2 (2026-11, #2567)` and a new section "7. Staged package
reconciliation" with the D1-D14 table, each row carrying: canonical source repo, revision, path, sha256
of that file at that revision (computed by the implementer with `git show <rev>:<path> | sha256sum`;
UNKNOWN where the source repo is not readable), staged value, corrected value, owner, status
(FIXED / UNKNOWN / OWNED-ELSEWHERE). Pinned sources add G = the PR's base commit and #2563 head
`6464978` (UNMERGED). M14-M16 are marked FIXED with a pointer to D5/D6/D7/D12/D14. Section 5 and a
new section 8 record downstream activation PR boundaries:

1. #2563 (DB roles, migration job, mctl-api env) — staged, inert.
2. P1 prep: copy provider/control values and netpols to target paths, tenant creation, control
   Temporal namespace — separate P1 issue + owner approval, after the Temporal path gates.
3. P2: facade to `services/labs/glovo-mcp`, `reservedPlatformHosts`, ingress on, OAuth protected
   resource registration — separate P2 GO.
4. Missing evidence listed as UNKNOWN: image names (provider, control), digests, mctl-api port and
   in-cluster vs public path, credential issuer (#2506/#2540), live Temporal namespaces.

### Runbook

`docs/runbooks/glovo-m1.md` sections "P1 checklist", "P2 checklist", "Negative test matrix" and
"Kill switch" updated to the new key names and policies; add negative checks: provider pod with
`TEMPORAL_HOSTPORT` set refuses to start; provider egress to `temporal:7233` and to the internet
times out; facade egress to `admins` control and `temporal` times out; public `/mcp` without a token
returns 401 with `WWW-Authenticate` naming the PRM URL; no Ingress object exists for provider/control.
These run in P1/P2, not now.

## Alternatives

1. **Fix only the manifests, leave the validator.** Rejected: the validator currently requires the
   obsolete values, so CI would fail; and the issue requires tests that fail before and pass after.
2. **Fold the DB roles/secrets into this PR.** Rejected: owned by #2563; duplicating creates two
   sources of truth for role names and Vault paths.
3. **Move the staged package into a reconciled path behind `ingress.enabled: false`.** Rejected:
   explicitly forbidden (inert, not picked up by Argo); `*.mctl.ai` has a proxied wildcard and the leak
   guard would refuse it.
4. **Delete the staged package and regenerate at P1.** Rejected: loses the reviewed P0 guard and
   crosswalk history; P1 would restart drift discovery.

## Platform impact

- Migrations: none. No reconciled file changes; ArgoCD sees nothing.
- Backward compatibility: only the staged package and its validator change. The `glovo-m1` CI job
  keeps the same entry points and exit codes (0/6/7).
- Resource impact: none at runtime; CI adds a few helm renders (seconds).
- Risks and mitigations:
  - Merge conflict with #2563 on `README.md`: keep README edits to the D14 section; rebase whichever
    lands second.
  - Encoding UNKNOWN values (mctl-api port, image names) as if correct: the validator treats
    `nameStatus: unknown` as not deployable and the crosswalk flags them; P1 must resolve them.
  - NetworkPolicy semantics checked by a hand-written helper may be incomplete: selftest cases cover
    each forbidden peer explicitly; kubeconform covers schema.
  - The facade credential path and Vault paths are plan-only names; they are not created and are
    labelled as proposals in `secrets-map.md`.
- Governance: this PR grants no deploy, activation or digest approval; P1 and P2 stay separate human
  gates.
