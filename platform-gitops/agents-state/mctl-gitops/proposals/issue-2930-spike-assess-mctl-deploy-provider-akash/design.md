# Design: issue-2930-spike-assess-mctl-deploy-provider-akash

Recommendation: **DEFER**. Do not add `--provider akash` (or any transacting
Akash command) to `cli/mctl` now. Authorize at most one isolated, offline
harness (Phase 0 below) whose output is a fixture, pinned validator commands,
negative cases and an estimate format, so the owner can later decide between
path C (thin SDL adapter) and path D (documentation only) on evidence.
`REJECT` is not chosen because a no-secret, stateless GPU worker is a real
gap in the current platform; `ADOPT_MINIMAL_ADAPTER` is not chosen because
no governed signing boundary exists and the core tool versions are not yet
pinnable from the observed sources.

## Current state

### CLI (read in the clone)

- `cli/mctl/cmd/root.go`: registers `deploy`, `delete`, `config`, `auth`,
  `repo`, `status`, `logs`, `version`. Only persistent flag is `--api-url`
  (`GetAPIURL`: flag > `MCTL_API_URL` > `https://api.mctl.ai`). No provider
  selector, no plugin mechanism.
- `cli/mctl/cmd/deploy.go` (`runDeploy`): flags `--team/-t`, `--name/-n`
  (required), `--repo/-r`, `--tag/-g`, `--port/-p` (default 8080), `--host`,
  `--dockerfile`, `--service-template`, `--image-tag`, `--env`, `--secret`
  (repeatable `KEY=VALUE`), `--wait/-w`, `--pat`. It derives
  `component_type` (`worker-service` when no host and default template),
  joins env/secret with `joinKV`, saves `--pat` straight to Vault through
  `internal/vault` (`SaveRepoPAT`, needs `VAULT_ADDR`/`VAULT_TOKEN`), then
  calls `client.ExecuteOperation("deploy-service", inputs)` with
  `action=onboard`, and optionally `PollWorkflow` for 10 minutes.
- `cli/mctl/internal/api/client.go`: `ExecuteOperation` posts to
  `/api/v1/operations/{op}/execute`; `PollWorkflow` reads
  `/api/v1/workflows/{name}`. The CLI holds no deployment logic of its own:
  build, Vault write, gitops commit and Argo CD sync are server-side.
- `cli/mctl/cmd/delete.go` (`retireServiceInputs`): forwards `confirm=yes`
  only after the operator typed DELETE or passed `-y`, because mctl-api
  marks `retire-service` `RequiresConfirm` (mctl-api#866). This is the
  existing precedent for "irreversible action needs explicit confirmation".
- `cli/mctl/cmd/status.go`, `logs.go`: read `/api/v1/status/{team}/{name}`
  and `/api/v1/logs/{team}/{name}`; both are Argo CD/Loki-backed.
- `cli/mctl/README.md`: OAuth sign-in via mctl-api (PKCE, loopback), token
  in `<config>/mctl/api-token.json`; credential precedence `MCTL_TOKEN` >
  `MCTL_AUTH` > stored sign-in. The token carries tenant/admin access.
- `cli/mctl/go.mod`: Go 1.26.9 floor; direct deps only cobra, go-oidc,
  go-jose, oauth2. Adding an Akash/Cosmos SDK would add a large dependency
  tree to a deliberately small module.
- `.github/workflows/cli-mctl.yml`: build, vet, govulncheck with
  `GOTOOLCHAIN: go1.26.11`, `GOVULNCHECK_VERSION: v1.7.0`; not a required
  check (paths filter). No release/signing job for the binary exists here.
- `cli/mctl/Makefile`: `LDFLAGS` injects
  `github.com/mctlhq/mctl-gitops/tools/mctl/cmd.version`, but the module is
  `github.com/mctlhq/mctl-gitops/cli/mctl`, so `mctl version` prints `dev`
  for `make build` output. Side observation; relevant because any Akash
  adapter would need a trustworthy CLI version in its audit lines.
- Repo-wide `grep -ril akash` (excluding `.git`): no matches. There is no
  existing Akash integration, SDL, or wallet reference anywhere.
- `infrastructure/k3s-preview/kube.tf`: control plane `cx33`, agent pool
  `cx43`, `location = "fsn1"`, load balancer in `fsn1`.
  `infrastructure/k3s-prod/README.md`: 3 control plane + 3+ workers. No GPU
  node pool appears in `infrastructure/` or any service values.

### Deployed state checked

- `mctl_whoami`: authenticated as `agent:issue-investigator`, admin false,
  teams `[]`, namespaces `[]`. Tenant-scoped reads (`mctl_get_tenant`,
  `mctl_list_services` per tenant) were therefore not attempted; this is a
  visibility gap, not evidence of absence.
- `mctl_get_operation deploy-service`: `minRole: developer`,
  `riskLevel: medium`, `requiresConfirm: false`, `secret_env_vars` marked
  `secret: true` and stored in Vault, `modifiesPaths:
  platform-gitops/services/{team_name}/{component_name}/`. There is no
  provider/target parameter: the operation always targets the MCTL cluster.
- Tool descriptions of `mctl_deploy_plan`, `mctl_request_deploy_approval`,
  `mctl_deploy_apply` (read from this run's tool list, not called): mctl-api
  already has an immutable plan -> owner fresh-sign-in grant -> single-use
  apply flow for previews. This is the governance shape any future path A
  would have to reuse.
- `$MCTL_GITOPS_ROOT/tenants/`: `admins`, `commerce-proof`, `karabu`,
  `labs`, `mctl`, `namax66`, `redloop`. `services/`: `admins`, `karabu`,
  `labs`, `namax66`, `redloop`.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`:
  image `ghcr.io/mctlhq/agent-worker-preview` pinned by digest, requests
  `cpu: 100m`, `memory: 128Mi`, `ephemeral-storage: 128Mi`. Used only as a
  sizing reference for the "disposable worker" profile; it is NOT proposed
  for migration (it is an agent worker and may handle credentials).
- `grep -ril gpu $MCTL_GITOPS_ROOT/services`: no matches.

### External sources (observed 2026-11-22 via WebFetch)

| # | Source | What it showed |
|---|--------|----------------|
| S1 | akash.network/docs/developers/deployment/akt/deployments/ | `akt sdl init web --image ...` and `akt sdl validate deploy.yaml` run "entirely locally, with no context, no key, and no RPC endpoint"; scaffolds `web`, `gpu`, `multi-service`, `ip-lease`; validate rejects unpinned images and warns on `uakt`. `akt deploy` does create / wait-for-bids / select-bid / create-lease / send-manifest; flags `--deposit`, `--bid-select`, `--yes`, `--dry-run`, `--no-wait-active`; `-o jsonl` emits one object per step. `akt update <sdl> <dseq>`, `akt close <dseq>` (irreversible). No current version stated. |
| S2 | .../akash-sdl/syntax-reference/ | `version: "2.0"`; sections `services`, `profiles.compute`, `profiles.placement`, `deployment`, optional `endpoints`; example `denom: uact` but comments say uakt per block (inconsistent); daily cost = amount x 14,400 / 1,000,000; cpu 0.01-384, memory 1Mi-2Ti, storage 5Mi-32Ti, one ephemeral volume required; `expose` with `port`, `as`, `proto`, `accept`, `to`, `global: true`. |
| S3 | .../learn/core-concepts/environment-secrets/ | SDL env is not encrypted; values reach the provider in the manifest and the container; not on-chain; recommends external secret store fetched at runtime. |
| S4 | .../learn/core-concepts/persistent-storage/ | Provider-local; data lost on lease close, not migrated across providers, may be lost on provider failure; back up externally. |
| S5 | .../learn/core-concepts/providers-leases/ | Lease states active / insufficient_funds (stopped, cannot restart without new deployment) / closed (permanent); escrow monitored by tenant; per-block (~6 s) billing; gas on updates; audited providers via `signedBy`; tier heuristics; providers can close leases. |
| S6 | .../api-documentation/getting-started/ | Go and TS SDKs exist (no module paths given); Console API = REST with managed wallet + API key; network data public; Blockchain SDK needs own wallet. |
| S7 | akash.network/pricing/gpus/ | "Prices updated November 20, 2026", averages from recent bids weighted by GPU count: H100 80GB SXM $2.73/GPU-h, A100 80GB SXM $1.67, RTX Pro 6000 96GB $2.27, RTX 5090 $0.58, RTX 4090 $0.36. |
| S8 | hetzner.com/cloud/ | Only category "from" prices excl. VAT: Cost-Optimized from EUR 5.99/mo, Regular Performance from EUR 5.49/mo, General Purpose from EUR 36.99/mo. No per-type figures. |

## Proposed solution

### Decision matrix (R1)

| Criterion | A: `--provider akash` via mctl-api | B: local `mctl akash` adapter that transacts | C: render/validate SDL, delegate to official `akt` | D: no adapter, document `akt` |
|---|---|---|---|---|
| MCTL OAuth identity on the action | Yes (server) | No (local key) | Only on render; execution is the user's own `akt` | No |
| Tenant binding / role check | Yes | No | Label only | No |
| Owner approval before spend | Possible via plan/grant/apply | No | No (outside MCTL) | No |
| MCTL audit + revocation | Yes | Local logs only | Render audit only | No |
| Secret handling | Needs new server mechanism; Vault not reachable from provider | Leaks risk into SDL/env | Blocked by design | User's problem |
| Signing key custody | mctl-api holds managed-wallet API key or chain key (new crown jewel) | User's laptop | User's laptop / Console | User |
| Build effort | Large (mctl-api provider backend, wallet ops, escrow monitor, lease reconciler) | Medium, and duplicates `akt` | Small | None |
| Maintenance vs upstream churn | High | High | Low (validator pinned) | None |
| Offline testability | Partial | Poor | Full | n/a |
| Risk of being mistaken for governed deploy | Low | High | Medium (mitigated by wording) | Low |
| Verdict now | DEFER | REJECT | Candidate after Phase 0 | Candidate after Phase 0 |

Smallest useful architecture, if Phase 0 succeeds: **C**, as a separate
`mctl akash sdl render|validate|estimate` subcommand group (never a
`--provider` flag on `mctl deploy`, so the governed command keeps a single
meaning). If Phase 0 shows that `akt sdl init/validate` already covers the
fixture and negative cases, choose **D** and only document. Path A is only
reconsidered after a separate GO that names a server-side signing boundary
and spend ceiling.

### What Akash adds and lacks vs ArgoCD/Hetzner

- Adds: on-demand GPU capacity (S7) that MCTL does not have at all (no GPU
  pool in `infrastructure/`); per-block billing suited to short-lived
  stateless jobs; no cluster to operate for disposable workers.
- Lacks for multi-tenant services: no Kubernetes API (no Argo CD, no
  ExternalSecrets/Vault, no NetworkPolicy, no `base-service` chart); ingress
  is provider-assigned unless `accept` hosts plus DNS are managed outside
  MCTL; no Loki/Prometheus scrape path (logs only via provider lease logs);
  data custody is the provider's (S3, S4); provider may close a lease (S5);
  no identity-bound workflow surface comparable to mctl-api grants.

### Flag mapping (R1)

Only applies to the future `mctl akash sdl render` command; `mctl deploy`
stays unchanged and gains no provider flag.

| Existing flag | Akash render behaviour | Reason |
|---|---|---|
| `--team/-t` | Required; recorded in the rendered SDL header comment and local audit line only | Preserves tenant label; does not imply tenant authorization |
| `--name/-n` | Required; SDL service and profile name (same pattern `^[a-z0-9][a-z0-9-]{0,30}$` as `deploy-service`) | Consistency |
| `--repo/-r`, `--tag/-g`, `--dockerfile`, `--service-template` | Rejected with error | No MCTL build path to Akash; Akash needs a pre-built image |
| `--image-tag` | Rejected; replaced by `--image <ref>@sha256:<digest>` | Tags are mutable; S1 validate rejects unpinned images |
| `--port/-p` | Mapped to `expose.port`; only one HTTP port in Phase 1 | Limited exposure |
| `--host` | Rejected in Phase 1 | `accept` hosts need DNS/TLS outside MCTL; stable ingress not provided |
| `--env` | Mapped to SDL `env` only after secret-pattern scan; refusal names the key only | S3: SDL env is plaintext to author and provider |
| `--secret` | Hard error before render, value never echoed | No vetted mechanism; Vault is not reachable |
| `--pat` | Hard error | No private repo build path; avoids Vault write side effect from `runDeploy` |
| `--wait/-w` | Rejected | Offline command has nothing to wait for |
| New `--max-monthly <amount> <unit>` | Required for `estimate` | User-configured cap |
| New `--region`, `--signed-by` | Mapped to `placement.attributes.region` / `signedBy` | Selection policy |

### CLI UX (proposal only, not to be implemented under this issue)

```
mctl akash sdl render   -t labs -n echo-fixture \
  --image ghcr.io/mctlhq/akash-fixture-http@sha256:<64-hex> \
  --port 8080 --cpu 0.5 --memory 512Mi --storage 1Gi \
  --region <region> --signed-by <auditor-address> \
  --price-amount 1000 --price-denom uact  > deploy.yaml
mctl akash sdl validate deploy.yaml      # wraps pinned `akt sdl validate`
mctl akash estimate deploy.yaml --max-monthly 20 ACT
```

Sample non-secret SDL (fixture; digest and auditor address are
placeholders until Phase 0 publishes a real fixture image):

```yaml
---
# rendered by mctl akash sdl render; team=labs; NOT an MCTL governed deployment
version: "2.0"
services:
  echo-fixture:
    image: ghcr.io/mctlhq/akash-fixture-http@sha256:<64-hex>
    env:
      - LOG_LEVEL=info
    expose:
      - port: 8080
        as: 80
        proto: tcp
        to:
          - global: true
profiles:
  compute:
    echo-fixture:
      resources:
        cpu:
          units: 0.5
        memory:
          size: 512Mi
        storage:
          - size: 1Gi
  placement:
    dcloud:
      attributes:
        region: <region>
      signedBy:
        anyOf:
          - <auditor-address>
      pricing:
        echo-fixture:
          denom: uact
          amount: 1000
deployment:
  echo-fixture:
    dcloud:
      profile: echo-fixture
      count: 1
```

Sample `estimate` output (format only; every number is model arithmetic):

```
PLAN (read-only, offline) -- NOT an MCTL governed deployment
team: labs   service: echo-fixture   sdl-digest: sha256:...
price ceiling: 1000 uact per block  (block ~6 s, 14,400 blocks/day)
  = 14.4 ACT/day = ~432 ACT/30d   [model-arithmetic, S2 formula]
ACT -> fiat: NOT CONVERTED (rate not observed; check before funding)
deposit/escrow: required by chain context, refundable remainder on close
                (amount not modelled)                       [not-observed]
gas: per create/update/close tx                              [not-observed]
monthly cap: 20 ACT  -> ceiling EXCEEDS cap: would refuse to proceed
providers/bids: none queried; no provider availability is implied
```

### State model (for any later funded step)

`rendered -> validated -> estimated -> [owner GO] -> created(dseq) ->
bids-received -> lease-active(dseq, gseq, oseq, provider) ->
(insufficient_funds | closed)`. `create`, `select-bid`, `create-lease`,
`send-manifest` map to `akt -o jsonl` step names (S1). Idempotency key =
`team/name/sdl-digest`; a second create with the same key is refused while a
dseq for it is open. A failure after `create-deployment` is reported as
`partial: dseq=<n> state=<s>`, never as rolled back. `close` is its own
command needing explicit confirmation of the exact dseq (precedent:
`retireServiceInputs` `confirm=yes`). Status/logs parity: `akt` lease status
/ logs keyed by dseq; no Loki ingestion.

### Governance mapping (R3)

- MCTL OAuth + tenant role + grant + audit exist only on mctl-api
  operations. `mctl akash sdl *` calls none of them; a user running
  `akt deploy` with their own key bypasses all of them. Therefore any output
  of path C must print "NOT an MCTL governed deployment", and docs must not
  call it one.
- A governed path (A) would require: mctl-api operation `akash-deploy` with
  `minRole`, `requiresConfirm`, plan/grant/apply reuse, a server-held
  managed-wallet API key in Vault, escrow monitor, lease reconciler and
  orphaned-lease alert. Not designed further here.

### Threat model summary

| Asset / surface | Threat | Phase 1 control |
|---|---|---|
| Wallet key / Console API key | Theft, unbounded spend | Not touched; harness never reads keyring or env keys |
| `akt` subprocess env | Inherits `MCTL_TOKEN`, `VAULT_TOKEN`, `GITHUB_TOKEN` | Harness runs `akt` with a scrubbed env (`env -i PATH=...`) |
| stdout/stderr JSONL | Logs leak values / manifests | Only `sdl validate` output captured; secret scan before write |
| SDL / manifest | Plaintext env to provider (S3) | Secrets blocked; env secret-pattern scan |
| Provider runtime | Full access to container memory/disk | Only public, no-secret, no-PII fixture |
| Image pull creds | Leak to provider | Public image only, digest-pinned |
| TLS / ingress | Provider-terminated or plain | `--host` rejected; fixture serves no sensitive data |
| Egress | Container can reach anything | Fixture makes no outbound calls by design |
| Eviction / provider close (S5) | Silent outage | Disposable workloads only |
| Persistent storage (S4) | Data loss | `persistent: true` rejected |
| Chain/lease errors, escrow drain | Orphaned paid lease | Out of scope until funded GO; alert design required then |

### Cost (R4)

| Profile | Akash | MCTL/Hetzner closest | Label |
|---|---|---|---|
| CPU-S 0.5 vCPU / 512Mi / 1Gi | not-observed | share of a `cx43` agent node (fsn1); per-type price not observed (S8 only "from" EUR 5.49-5.99/mo) | not-observed |
| CPU-M 2 vCPU / 4Gi / 10Gi | not-observed | share of `cx43` | not-observed |
| CPU-L 4 vCPU / 8Gi / 20Gi | not-observed | roughly a dedicated `cx33`-class node (spec to be pinned) | not-observed |
| GPU RTX 4090 x1 | $0.36/GPU-h avg (S7, 2026-11-20) -> ~$262.80 per 730 h | none (no GPU pool) | observed-public avg / model-arithmetic |
| GPU H100 80GB x1 | $2.73/GPU-h avg (S7) -> ~$1,992.90 per 730 h | none | observed-public avg / model-arithmetic |

No saving is claimed: no CPU price was observed, the GPU figures are
averages not bids, and MCTL has no same-resource GPU option to compare.
Unmodelled on the Akash side: escrow capital lock, gas, ACT/fiat rate,
ingress/IP lease fees, transfer, operator time to watch escrow, and
downtime from provider close.

### First useful workload

A disposable, no-secret, stateless HTTP echo fixture (Phase 0/1), then at
most a disposable GPU batch job over public data (e.g. a public-model
inference benchmark). Safer than migrating production services because it
holds no credentials, no tenant data and no state, and loss of the lease
loses nothing.

### Hard stop / no-go factors

- Cannot pin an `akt` release and checksum from an official source.
- Validator does not reject unpinned images / bad denoms deterministically.
- No mechanism to enforce a spend ceiling before signing.
- Lifecycle not observable enough to detect orphaned leases or escrow drain.
- Any design that requires putting a real secret into SDL env.
- Any design where an ungoverned local signature is reported as governed.

### Independent review (evidence-led)

- P1: No signing boundary inside MCTL governance exists (CLI is a thin
  mctl-api client; `deploy-service` has no provider parameter). Any
  transacting adapter now would be ungoverned. -> blocks ADOPT.
- P1: Secrets: `--secret`/`--pat` today go to Vault (`runDeploy`,
  `SaveRepoPAT`); Akash has no equivalent, SDL env is plaintext (S3). ->
  hard block in Phase 1.
- P2: Tool versions unpinned (S1 states none) and denom docs inconsistent
  (S2). -> Phase 0 must pin before trusting results.
- P2: CLI version stamping broken (`Makefile` LDFLAGS path), weakening any
  audit line that cites CLI version. -> separate fix, outside this issue.
- P3: No CPU price evidence; GPU only averages. -> cost case unproven.

## Alternatives

- **A: governed `mctl deploy --provider akash` via mctl-api.** Dropped for
  now: needs a new server-held wallet key, escrow/lease reconciler and a
  new operation, i.e. a second deployment engine in mctl-api, with no
  evidence yet of value.
- **B: local transacting `mctl akash deploy`.** Rejected: duplicates `akt`
  and uses the user's own key, so it bypasses OAuth/tenant/approval/audit
  while carrying the `mctl` brand.
- **Native Go SDK inside `cli/mctl`.** Dropped: module paths and SDL APIs
  not observed (S6); would add a Cosmos-scale dependency tree to a module
  with four direct deps and a govulncheck gate.
- **Console API.** Dropped for Phase 1: needs an API key and managed wallet
  (S6), i.e. a funded account, which the issue forbids.

## Platform impact

- No change to any manifest, chart, workflow, CLI code or tenant. This
  proposal adds only documents.
- Phase 0 (if accepted) adds a self-contained harness directory under
  `docs/spikes/akash/` (fixture SDL, negative SDLs, a script that runs a
  pinned `akt sdl validate` with a scrubbed env) and no CI required check.
- Risk register:
  - R-1 ungoverned spend mistaken for MCTL deploy -> no `--provider` flag,
    mandatory "NOT governed" banner.
  - R-2 secret leakage into SDL -> hard block + scan, negative tests.
  - R-3 upstream `akt` churn -> exact version + checksum pin.
  - R-4 orphaned paid lease -> out of scope until funded GO with cleanup.
  - R-5 data loss -> persistent storage rejected.
- Boundary: everything above is offline research. A testnet/sandbox
  experiment would prove bid/lease/manifest/close round-trip, JSONL step
  parsing and close semantics; it must use a dedicated throwaway key, a
  fixed small testnet balance, the fixture image only, and end with a
  verified `close`. A mainnet lease needs a new explicit owner GO naming a
  spend ceiling, the funded account authority and a cleanup approval.
