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
`ExecuteOperation`). Every governed property (OAuth identity, tenant role
`minRole: developer`, Vault-backed secrets, Argo Workflow audit) lives
server-side in mctl-api, not in the CLI. A local `akt` transaction signed by
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
- IF an `--env` value matches a secret-looking pattern (high-entropy token,
  known key prefixes such as `sk-`, `ghp_`, `AKIA`, PEM headers) THEN THE
  SYSTEM SHALL refuse to render the SDL and SHALL report only the key name.
- IF the image reference is not pinned by `@sha256:` digest THEN THE SYSTEM
  SHALL refuse to render or validate the SDL.
- IF a pricing denom other than the one the pinned validator version
  accepts as current (expected `uact`, to be confirmed against the pinned
  tool) is supplied THEN THE SYSTEM SHALL refuse it.
- IF a service exposes a database or non-HTTP port with `global: true`
  THEN THE SYSTEM SHALL refuse the SDL in Phase 1.
- IF any persistent storage volume (`persistent: true`) is requested THEN
  THE SYSTEM SHALL refuse the SDL in Phase 1.
- WHILE operating in offline mode THE SYSTEM SHALL make no network call,
  read no wallet key, keyring or Console API key, and invoke no `akt`
  subcommand other than `akt sdl validate` / `akt sdl init`.
- WHEN a read-only estimate is shown THE SYSTEM SHALL display the price
  unit and block interval, the conversion formula, the currency-conversion
  caveat, deposit/escrow and gas as separate lines, and the user's monthly
  cap, and SHALL state that no provider availability or bid was observed.
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
  acceptance of its content digest.

## Open questions

- Current `akt` release version and install/pinning channel: the deployment
  lifecycle page (observed 2026-11-22) names no version except a historical
  "akt 0.1.x" note. The harness task must pin an exact release and checksum
  before any validation result is trusted.
- Pricing denom: the SDL syntax reference shows `denom: uact` in its example
  but its placement comments still describe amounts as uakt per block; the
  `akt` lifecycle page says `akt sdl validate` warns on `uakt`. Treat `uact`
  as current only after confirming against the pinned validator.
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
