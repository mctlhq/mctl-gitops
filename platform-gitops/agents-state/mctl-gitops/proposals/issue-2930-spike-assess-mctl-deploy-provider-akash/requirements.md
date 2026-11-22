# Spike: assess `mctl deploy --provider akash` (SDL, bidding, governance, cost)

## Context

Issue mctlhq/mctl-gitops#2930 asks whether the existing Go/Cobra CLI at
`cli/mctl` can safely offer an opt-in `mctl deploy --provider akash` route
while keeping MCTL identity, tenant binding, owner approval and audit, and
without reimplementing Akash's deployment engine. The scope is research only:
a source-pinned comparison, this requirements/design/tasks proposal, and a
reasoned `ADOPT_MINIMAL_ADAPTER | DEFER | REJECT` recommendation. No wallet,
chain transaction, Console account, lease, production change, secret access
or implementer run happens under this issue.

Today `mctl deploy` (`cli/mctl/cmd/deploy.go`, `runDeploy`) only builds a
`deploy-service` `action=onboard` request and posts it to
`/api/v1/operations/deploy-service/execute` (`internal/api/client.go`,
`ExecuteOperation`). The existing `deploy-service` path enforces tenant authorization (`minRole:
developer`) server-side and orchestrates Vault-backed secrets and Argo Workflow
audit; the CLI is not an independent enforcement boundary. A local `akt` transaction signed by
a user's own key would carry none of them. This proposal's recommendation is
**DEFER** any governed or transacting Akash route, and authorize at most an
**isolated offline harness** (fixture SDL, pinned validator, negative cases,
read-only estimate format) as the next bounded step, kept outside `cli/mctl`
until its findings are reviewed.

## User stories

- AS the platform owner I WANT a source-pinned decision matrix for Akash
  integration paths A-D SO THAT I can accept or refuse a next step by exact
  content digest, without anything having been signed or paid.
- AS a tenant developer I WANT `mctl` to refuse any Akash-related input it
  cannot govern SO THAT a secret, PAT or unsupported flag is never silently
  dropped, leaked into an SDL, or presented as an MCTL governed deployment.
- AS a security reviewer I WANT a threat model and risk register covering
  signing keys, subprocess environment, JSONL output, provider manifests,
  provider runtime access, ingress/egress and orphaned leases SO THAT any
  later funded proof starts from documented stop conditions.
- AS a cost owner I WANT observed public prices separated from model
  arithmetic and from live bids SO THAT no cost saving is claimed without a
  same-resource, same-region, same-SLO comparison.
- AS a future implementer I WANT an offline fixture and exact validator
  commands SO THAT the first code change (if ever approved) can be tested
  deterministically with no network and no keys.

## Acceptance criteria (EARS)

Deliverable criteria (this spike):

- WHEN the proposal is reviewed THE SYSTEM SHALL contain a decision matrix
  comparing paths A (governed dispatch via mctl-api), B (local CLI adapter
  `mctl akash ...` / `--dry-run`), C (generate/validate SDL, delegate
  execution to official `akt`) and D (no adapter, documentation only) on
  governance, secrets, maintenance, offline testability and value, with an
  explicit recommendation of exactly one of `ADOPT_MINIMAL_ADAPTER`, `DEFER`,
  `REJECT`.
- WHEN an external fact is cited THE SYSTEM SHALL name its URL and the date
  it was observed (2026-11-22 unless stated), and SHALL mark facts the
  source page does not state (for example the current `akt` version) as
  unobserved rather than inferred.
- WHEN prices are presented THE SYSTEM SHALL label each figure as one of
  `observed-public`, `model-arithmetic` or `not-observed`, and SHALL NOT
  present any figure as an observed bid.
- THE SYSTEM SHALL map every existing `mctl deploy` flag (`--team`,
  `--name`, `--repo`, `--tag`, `--port`, `--host`, `--dockerfile`,
  `--service-template`, `--image-tag`, `--env`, `--secret`, `--wait`,
  `--pat`) to exactly one of: mapped, rejected-with-error, or not-applicable;
  no flag may be silently ignored.

Behavioural criteria for any later offline harness or adapter (binding on
future work, not implemented here):

- IF `--secret` or `--pat` is passed together with an Akash provider or
  Akash subcommand THEN THE SYSTEM SHALL exit non-zero before any SDL is
  rendered, and SHALL NOT print, write or log the value.
- IF an environment key is not on an explicit allowlist of non-sensitive
  fixture keys (initially `LOG_LEVEL` and `PORT`) THEN THE SYSTEM SHALL reject
  it before any file/stdout render. In Phase 0, heuristic secret-pattern
  scanning SHALL be defense-in-depth only; reject every `--secret`, `--pat`,
  `credentials`, or other sensitive SDL field even when the value does not
  match a token pattern. Error diagnostics may name keys but never values.
- IF the image reference is not pinned by a full `@sha256:` digest THEN THE
  SYSTEM SHALL refuse to render or validate the SDL **in MCTL policy before
  calling `akt`**; native `akt` accepts ordinary explicit tags, so its
  successful validation is insufficient evidence of digest pinning.
- IF pricing denom is not `uact` THEN MCTL policy SHALL reject it even if
  the pinned `akt` validator merely warns; record the upstream v1.1.x
  behavior and any protocol change rather than inferring it. Units must
  display as micro-ACT (nominally USD-pegged ACT), not AKT.
- IF a service exposes a database or non-HTTP port with `global: true`
  THEN THE SYSTEM SHALL refuse the SDL in Phase 1.
- IF any persistent storage volume (`persistent: true`) is requested THEN
  THE SYSTEM SHALL refuse the SDL in Phase 1.
- WHILE executing the offline validation phase THE SYSTEM SHALL be confined
  to a network-disabled runtime with temporary empty HOME, XDG directories,
  and `AKT_HOME`, scrubbed subprocess environment and no mounted wallet,
  keyring or Console API key. The validation phase SHALL invoke only pinned
  `akt sdl validate` / `akt sdl init`; acquiring the verified release and
  fixture image digest is an explicit **separate, networked preparation**
  phase that never runs under the offline/no-network claim.
- WHEN a read-only estimate is shown THE SYSTEM SHALL display the price
  unit (`uact`), approximate block interval, conversion formula to ACT
  (nominal 1 ACT = 1 USD per current upstream docs; *not* AKT market price),
  actual price/peg uncertainty, deposit/escrow or Console credit path,
  gas/fees, and the user's monthly cap, and SHALL state that no provider
  availability or live bid was observed. A cap displayed by an offline
  estimator is advisory only; it SHALL NOT be represented as an enforceable
  spend limit for any future signing path.
- THE SYSTEM SHALL NOT describe any locally signed `akt` transaction as an
  MCTL governed deployment, in output text, docs or audit records.
- IF a future funded step reports a failure after on-chain state was
  created THEN THE SYSTEM SHALL report the dseq/lease identifiers and the
  residual state, and SHALL NOT report the deploy as fully rolled back.
- WHEN a future step would run `akt close` THE SYSTEM SHALL require an
  explicit, separate approval for that dseq, because close is irreversible.

## Out of scope

- Any code change under `cli/mctl/`, mctl-api, Argo Workflows or Helm charts.
- Funded wallets, Console accounts or API keys, testnet or mainnet
  transactions, bids, leases, manifests sent to providers.
- Moving any existing tenant service (for example `labs/mctl-telegram`,
  MTProto sessions, OAuth tokens, control-plane credentials) to Akash.
- Persistent production data on Akash.
- GPU procurement decisions.
- Approving or implementing this proposal; that needs separate owner
  acceptance of its content digest. **Do not signal the live Temporal DevLoop
  approval while only reviewing or revising the proposal:** that approval
  can advance directly to the Tier 2 implementer. A future owner decision
  must explicitly authorize exactly the offline harness implementation,
  separately from this documentation review.

## Open questions

- Upstream `akt` release and checksum: GitHub releases showed **v1.1.2**
  as latest in the independent 2026-11-23 review; official installation
  docs document downloadable SHA-256 manifest. An actual artifact checksum,
  platform/architecture, release provenance and validated binary are **not
  yet pinned**. Phase 0 must record and verify all of these before trusting
  validation output.
- Pricing denom: the current `akt` lifecycle guide says `uact` is micro-ACT
  with 1:1 USD nominal accounting; a legacy `uakt` value may only warn at
  validation and fail at deploy-time if deposit denominations mismatch.
  The SDL syntax page still incorrectly describes its `uact` example using
  `uakt` and `AKT`. Policy MUST reject non-`uact` before estimating; verify
  behavior with a pinned binary and pin the source pages in the report.
- Whether the Go SDK exposes an SDL parser usable without pulling a full
  chain client: the API getting-started page (observed 2026-11-22) names Go
  and TS SDKs but no module paths or SDL functions. Not observed.
- Akash public CPU-only prices: only GPU averages were observed (pricing
  page, "Prices updated November 20, 2026"). CPU profile prices are
  `not-observed` in this run.
- Exact Hetzner prices for the `cx33`/`cx43` types used in
  `infrastructure/k3s-preview/kube.tf`: the Hetzner cloud landing page gave
  only "from" category prices. Must be pinned from the plan pages.
- Whether the owner wants a future governed path to live in mctl-api (path
  A, server-held managed-wallet key) at all; this spike recommends against
  deciding that until the offline harness results exist.

## Independent review gates (2026-11-23; reviewer amendment draft)

- **P1 / approval coupling:** approving a live Temporal DevLoop is an
  execution action, not a read-only signoff. This PR does not approve the
  current proposal or start Tier 2. New owner GO, reviewed digest and bounded
  implementation scope are required before any approval signal.
- **P1 / secrets:** no secret may enter fixture SDL or output even if it
  evades regex detection. Synthetic canaries are held only in memory and
  compared against captured/sanitized output; never commit canaries in
  negative fixture files. Negative cases that a validator would echo must
  be rejected by the MCTL preflight policy *before* invoking `akt`.
- **P1 / immutability:** `akt` accepts explicit image tags. A digest-only
  policy is MCTL-specific and must be tested independently.
- **P2 / reproducibility:** pin the actual `akt` release artifact and checksum
  (not just `latest`), use an unprivileged sandbox with network disabled
  and credential-free temporary HOME. Separate acquisition from offline runs.
- **P2 / price:** distinguish `uact`/ACT from `uakt`/AKT, expose actual vs
  hypothetical bid and non-enforceable offline caps. Fix inconsistent upstream
  documentation by recording—not repeating—the error.
- **P2 / fixture:** generate an actually validator-valid minimal SDL with
  no invented `signedBy` address or restrictive region. Provider filters and
  their real semantics are research subjects, not requirements for fixture
  validation.
- **P3 / economics:** CPU comparison currently unobserved; GPU published
  averages do not establish a cheaper equivalent deployment.

Independent upstream evidence (reviewed 2026-11-23):
- https://akash.network/docs/developers/deployment/akt/deployments/
- https://akash.network/docs/developers/deployment/akt/installation/
- https://akash.network/docs/developers/deployment/akash-sdl/syntax-reference/
- https://github.com/akash-network/akt/releases/tag/v1.1.2

**GO remains `GO_RESEARCH`, not `GO_OFFLINE_HARNESS`.** The reviewed and
merged revision plus an explicit owner decision are prerequisites to
executing tasks 1–6.
