# Spike #891: Sign in with ChatGPT (SIWC) as end-user BYOS in the existing mctl CLI

## Context

Issue mctlhq/mctl-agents#891 asks a spike question. Can a normal MCTL user attach their own eligible ChatGPT subscription to the existing Go CLI (`mctlhq/mctl-gitops/cli/mctl`) through Sign in with ChatGPT (SIWC), so that MCTL can run eligible inference on that user's own plan with no API key? MCTL governance (tool policy, approvals, capability scope, evidence) must stay authoritative. The design must not depend on owner-only identity or infrastructure. The owner account may be used only for a manual live dogfood measurement. The spike ends with exactly one of these recommendations: `ADOPT_SIWC_MCTL_CLI`, `ADOPT_SIWC_CLI_PLUS_CODEX`, `ADOPT_SIWC_CLI_PLUS_THIN_ADAPTER`, `DEFER_COMMERCIAL_HOSTED_ACCESS`, `REJECT_SIWC_FOR_MCTL`.

This matters for three reasons. The CLI already has a vetted browser OAuth flow: dynamic client registration, loopback redirect, PKCE S256, state and nonce checks, owner-only credential files, and lock-serialized rotation of refresh tokens (`cli/mctl/internal/auth/api.go`, `internal/auth/zitadel.go`). So SIWC can probably reuse proven patterns rather than add a new runtime. The only provider seam in mctl-agents (#824, `config/model_policy.py`) accepts `api: anthropic-messages` only, and it runs inside the shared `admins` cluster workers. So the spike has to settle where an OpenAI Responses credential belongs, and where it must never go. The deliverable is evidence plus a recommendation: a spike report, an isolated experiment and a fake-auth CI fixture. Production code changes to `cli/mctl` are follow-ups that the owner gates on the verdict.

## User stories

- AS a normal (non-admin) MCTL user I WANT to connect my own ChatGPT subscription from `mctl` SO THAT eligible MCTL agent work runs on my own plan quota without an API key.
- AS that user I WANT `mctl auth status` to show my MCTL identity and my ChatGPT inference identity as separate things SO THAT I always know which account pays for inference.
- AS that user I WANT to disconnect only my ChatGPT credential SO THAT my MCTL sign-in keeps working.
- AS that user I WANT to see the models my own account is entitled to SO THAT I never choose a model my plan cannot serve.
- AS the platform owner I WANT to dogfood the same generic flow SO THAT the live measurement proves the end-user design, not a special owner path.
- AS the spike owner I WANT a policy matrix with sources for each deployment shape SO THAT shared or hosted MCTL surfaces never inherit a subscriber's plan.
- AS a reviewer I WANT a CI fixture that uses only fake OAuth and Responses servers SO THAT no real token is ever needed or exposed in CI.

## Acceptance criteria (EARS)

Report and decision
- WHEN the spike completes THE SYSTEM SHALL provide `docs/spikes/891-siwc-byos.md` with a current-state map of `cli/mctl` auth, config and credential ownership; the end-user journey from `mctl auth login` to the first SIWC-backed inference; the policy matrix; the measurements table; and a `## Decision` section with exactly one token from the Outcomes list.
- WHEN the policy matrix is written THE SYSTEM SHALL give each of the 10 deployment shapes in the issue exactly one of `ALLOWED`, `NOT_ALLOWED` or `NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS`, with a source URL, the date it was read and the architectural consequence.
- IF a policy rule cannot be found in a current OpenAI source THEN THE SYSTEM SHALL classify the shape conservatively (`NOT_ALLOWED` or `NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS`), mark the evidence as `UNSOURCED`, and never as `ALLOWED`.
- WHEN a measurement was not taken THE SYSTEM SHALL record it as `UNMEASURED`, never as zero or absent.
- WHEN a result was observed only on the owner account THE SYSTEM SHALL label it `owner-dogfood-only` and keep it apart from the behaviours proven generically by the fake fixture.
- WHEN the report compares the integration options THE SYSTEM SHALL score the 7 use cases in the issue on user experience, MCTL identity, inference identity, credential owner, runtime owner, quota owner, policy fit, operational burden and failure UX.
- IF neither the direct-CLI path nor the CLI-plus-Codex path demonstrates a concrete need for a long-lived local process THEN THE SYSTEM SHALL record `NO_ADAPTER_NEEDED_FOR_SIWC` and shall not exercise the #746 thin adapter.

Auth proof (experiment `experiments/siwc-cli-891/`)
- WHEN a user runs the experiment's `auth openai login` THE SYSTEM SHALL perform documented dynamic client registration, run a loopback (127.0.0.1) authorization-code flow with PKCE S256, validate state before the code exchange, validate the ID-token nonce, and send a persisted opaque `ext_agent_host_id`.
- WHEN the token exchange succeeds THE SYSTEM SHALL verify the ID token and confirm that the granted scopes include ChatGPT plan usage before storing anything.
- IF the grant lacks the plan-usage entitlement THEN THE SYSTEM SHALL store no inference credential and shall print an actionable "account not eligible" message.
- WHEN credentials are stored THE SYSTEM SHALL write them to a SIWC-only file, separate from `api-token.json` and `zitadel-token.json`, owner-only (mode 600) and through temp-file-plus-rename. The file shall hold the issued `client_id` for later refresh and re-authorization.
- WHILE two or more processes refresh the same SIWC credential concurrently THE SYSTEM SHALL serialize the refresh under a lock file so that each rotated refresh token is presented at most once.
- WHEN the user runs `auth openai logout` THE SYSTEM SHALL remove the local SIWC tokens, attempt revocation where a documented endpoint exists, and report whether the revocation was confirmed. It shall leave the MCTL control-plane sign-in untouched.
- WHILE any SIWC operation runs THE SYSTEM SHALL never print a token, pass it in argv, write it to a CI artifact, or send it to mctl-api, Vault, GitOps or GitHub Actions.
- THE SYSTEM SHALL never read `~/.codex`, ChatGPT browser cookies or any other client's OAuth credentials.

Models and inference
- WHEN the user lists models for provider `openai` THE SYSTEM SHALL query the account-specific model-discovery path with the user's own credential and show only the returned catalog. There shall be no hard-coded global model list.
- IF the login is valid but the catalog is empty or the entitlement is missing, or a previously chosen model is no longer listed, or the request is refused for quota or rate limits, THEN THE SYSTEM SHALL return a distinct, stable reason code and message for each case.
- WHEN the bounded fixture runs on the direct Responses path THE SYSTEM SHALL cover plain reasoning, one client-side function-call round trip, multi-turn continuation with client-managed history (`store: false`), and the expired, revoked and usage-limited grant cases.
- WHILE a model proposes a tool call THE SYSTEM SHALL execute only tools in the MCTL-approved allowlist. Any other call shall be refused locally, so provider or model choice never bypasses MCTL policy.

Identity boundary
- THE SYSTEM SHALL contain no code path keyed on admin or owner identity. A CI test shall prove that the SIWC flow completes when the fake MCTL `whoami` returns `isAdmin: false` and no groups.
- THE SYSTEM SHALL never let one user's SIWC credential serve another user's request, and shall expose no general-purpose OpenAI proxy.

CI
- WHEN the spike's CI runs THE SYSTEM SHALL use fake OAuth, model-discovery and Responses servers only, and shall need no secrets.

## Out of scope

- Changing `mctlhq/mctl-gitops/cli/mctl` itself. That is a follow-up after the owner records the verdict.
- An owner-only inference path, or using the owner's plan for tenant or user work.
- A new `mctl-runtime` CLI or daemon. The #746 thin adapter is evaluated only if a need is proven.
- Adding an OpenAI/Responses `api` value to `config/model_policy.py` (#824 seam), or routing any mctl-agents worker through SIWC.
- Changing mctl-support's production provider (`MODEL_PROVIDER: nebius`) or any tenant credential.
- Broad model benchmarking (#791), account pooling or rotation, API proxying, production rollout.
- Storing SIWC tokens in mctl-api, Vault, GitOps, GitHub Actions or any shared MCTL service.

## Open questions

- These SIWC details are not stated on the source page read on 2026-10-29 and must be taken from the linked SIWC sign-in, models-and-inference and errors-and-recovery pages during the spike: the exact scope names, the model-discovery endpoint, the revocation endpoint and semantics, and the rules on another user's activity, proxying, pooling and background automation. Until then they are `UNSOURCED`.
- Should logout also forget the persisted `client_id` and `ext_agent_host_id`? The docs say re-sign-in does not create a new host, which argues for keeping them. This proposal keeps both by default and adds an explicit `--forget-client` flag. The owner may prefer otherwise.
- Codex app-server credential handoff: it is unknown whether app-server accepts an externally owned SIWC access token over its JSON-RPC protocol without writing `~/.codex/auth.json`. If it does not, credential ownership moves to Codex and option 2 conflicts with invariants 4 and 5. The spike records this outcome rather than working around it.
- The live dogfood run needs a human with a browser and an eligible plan. If no one runs it, every live field stays `UNMEASURED` and the decision must rest on the fake fixture plus the sourced policy.
- `cli/mctl` has no CI workflow in mctl-gitops `.github/workflows/`, and its Makefile stamps the version through `github.com/mctlhq/mctl-gitops/tools/mctl/cmd.version`, while the module path is `.../cli/mctl`. Both are noted as follow-up candidates. Neither blocks the spike.
