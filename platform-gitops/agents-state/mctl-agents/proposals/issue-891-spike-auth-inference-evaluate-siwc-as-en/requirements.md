# Spike #891: Sign in with ChatGPT (SIWC) as end-user BYOS in the existing mctl CLI

## Context

> **2026-11-19 scope refinement — necessity before implementation.** The existing [Codex/MCTL Bridge](https://github.com/mctlhq/mctl-claude-remote/blob/main/docs/chatgpt-orchestrator-bridge.md) already resumes a durable Codex thread, starts turns and returns answers to Claude slots. This spike must first demonstrate whether SIWC adds meaningful *incremental* value versus that running baseline. Preserve the primary #891 end-user BYOS hypothesis; a private-bridge NO-GO does not automatically imply a BYOS NO-GO. Do not equate a new Responses conversation with waking a particular standard ChatGPT web chat.

Issue mctlhq/mctl-agents#891 asks a spike question. Can a normal MCTL user attach their own eligible ChatGPT subscription to the existing Go CLI (`mctlhq/mctl-gitops/cli/mctl`) through Sign in with ChatGPT (SIWC), so that MCTL can run eligible inference on that user's own plan with no API key? MCTL governance (tool policy, approvals, capability scope, evidence) must stay authoritative. The design must not depend on owner-only identity or infrastructure. The owner account may be used only for a manual live dogfood measurement. The spike ends with exactly one of these recommendations: `ADOPT_SIWC_MCTL_CLI`, `ADOPT_SIWC_CLI_PLUS_CODEX`, `ADOPT_SIWC_CLI_PLUS_THIN_ADAPTER`, `DEFER_COMMERCIAL_HOSTED_ACCESS`, `REJECT_SIWC_FOR_MCTL`.

This matters for three reasons. The CLI already has a vetted browser OAuth flow: dynamic client registration, loopback redirect, PKCE S256, state and nonce checks, owner-only credential files, and lock-serialized rotation of refresh tokens (`cli/mctl/internal/auth/api.go`, `internal/auth/zitadel.go`). So SIWC can probably reuse proven patterns rather than add a new runtime. The only provider seam in mctl-agents (#824, `config/model_policy.py`) accepts `api: anthropic-messages` only, and it runs inside the shared `admins` cluster workers. So the spike has to settle where an OpenAI Responses credential belongs, and where it must never go. The deliverable is evidence plus a recommendation: a spike report, an isolated experiment and a fake-auth CI fixture. Production code changes to `cli/mctl` are follow-ups that the owner gates on the verdict.

## Owner-scoped decision — 2026-11-22: GO_LOCAL_SIWC_CODEX_RESEARCH

**Selected research/pilot direction (not a final implementation verdict):** user-owned ChatGPT SIWC → existing `mctl` CLI (distinct OAuth credential namespace) → locally spawned Codex app-server over stdio → MCTL-authorized tools and approvals. Direct SIWC Responses and the existing authenticated Codex/MCTL Bridge remain measured baselines; do not pre-select the final #891 Outcomes token before evidence. Source-pinned upstream policy research: [mctl-agents#1110 report, 0d22925](https://github.com/mctlhq/mctl-agents/blob/0d22925fdfdbcbad9afbc29673666b9e4d8dce78/docs/spikes/1110-subscription-backed-inference-research.md).

**Authorized now:** edit and independently review this existing proposed specification, plus a later *separately reviewed* isolated offline fake-OAuth/Responses/Codex fixture. The owner selected a preferred local architecture, **not** an approval of existing `.status.yaml`, not paid/live OAuth, not running the implementer, and not a merge/production authorization. Before work beyond spec revision, require an adopted owner decision on the exact reviewed content digest and approved bounded slice. Existing per-user local entitlement must be proven for each user.

**Hard prohibition:** never move the user's SIWC credentials into shared MCTL workers, mctl-api, Vault, GitOps, CI, another tenant, a hosted proxy, or a SaaS paid offering without explicit provider-granted access. No Google Antigravity consumer OAuth or third-party Claude.ai OAuth fallback. Model selection never bypasses MCTL approval, consent, capability lists, execution-token identity or audit.

**Official primary docs, verified 2026-11-22:** [OpenAI scope/registration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [Codex app-server integration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server), [preview restrictions](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations), [quota/account settings](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions), [same-user self-hosted VM caveat](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms), [OSS/local vs paid/remote](https://developers.openai.com/siwc/token-sharing-open-source). These are provider web pages, not immutable permission grants; re-check on live pilot day.

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

Necessity and baseline gate (before an expensive SIWC prototype)
- WHEN the investigation starts THE SYSTEM SHALL pin the existing Codex/MCTL Bridge source/release and record proven `thread/resume`, `turn/start`, response, correlation, recovery and credential boundaries using [bridge design](https://github.com/mctlhq/mctl-claude-remote/blob/main/docs/chatgpt-orchestrator-bridge.md), [bridge README](https://github.com/mctlhq/mctl-claude-remote/blob/main/plugin/mctl-bridge/README.md), and current code.
- WHEN comparing options THE SYSTEM SHALL distinguish (A) the **already working authenticated Codex app-server + MCTL Bridge**, (B) user-controlled SIWC → direct Responses as a proposed thin RPC/BYOS path, and (C) ordinary billed API-key Responses as policy/cost reference only. An external SIWC token handoff to a *newly spawned* Codex process is a distinct optional test, not the existing Codex baseline.
- THE SYSTEM SHALL score review/investigation, structured output, MCTL CLI BYOS and personal bridge against latency, correctness/tool-allowlist, history ownership, process/RSS overhead, credentials/refresh complexity, quota contention and supported deployment conditions. Measure using the same bounded fixtures, pin observed model/effort, and label non-equivalent models (no fabricated apples-to-apples claims).
- THE SYSTEM SHALL capture dated primary evidence for SIWC plan-usage scope, five-hour/weekly/app limits where documented, relationship to Codex quota, paid credit risk, and eligibility for local/user-hosted vs shared/remote/commercial automation. Record unresolved items as `UNSOURCED` or `UNMEASURED`, never infer independent quota from OAuth.
- THE SYSTEM SHALL report `bridge_incremental_value: YES | NO | UNPROVEN` **separately** from the existing issue-level SIWC outcomes, with concrete evidence, and explicitly label existing ChatGPT web-chat wake capability `SUPPORTED` only with documented, reproducible proof; otherwise `EXISTING_CHAT_WAKE_UNSUPPORTED`.
- IF a supported policy path or differentiated benefit cannot be established at the initial gate THEN the research may deliver a defensible `REJECT_SIWC_FOR_MCTL` / `DEFER_COMMERCIAL_HOSTED_ACCESS` recommendation without exercising paid/live inference or building optional execution adapters. Mark omitted live/prototype evidence `UNMEASURED` and explain the gate that stopped it. **Do not** mistake a lack of private-bridge benefit for rejection of end-user BYOS without evaluating that primary hypothesis.
- No login, live quota consumption, merge/deploy or downstream implementation approval is granted by this proposal update.

Auth proof (experiment `experiments/siwc-cli-891/`; **conditional on Gate 0 and separately authorized offline fixture slice**, T1–T13 in tasks.md are not mandatory on a DEFER/REJECT exit)
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

- Calling an arbitrary existing standard ChatGPT web conversation through undocumented RPC, browser/cookie/token extraction or session impersonation. SIWC Responses creates a separate client-managed context.
- Building a duplicate Codex bridge or reusing the platform owner's OAuth grant for shared tenant work.
- Changing `mctlhq/mctl-gitops/cli/mctl` itself. That is a follow-up after the owner records the verdict.
- An owner-only inference path, or using the owner's plan for tenant or user work.
- A new `mctl-runtime` CLI or daemon. The #746 thin adapter is evaluated only if a need is proven.
- Adding an OpenAI/Responses `api` value to `config/model_policy.py` (#824 seam), or routing any mctl-agents worker through SIWC.
- Changing mctl-support's production provider (`MODEL_PROVIDER: nebius`) or any tenant credential.
- Broad model benchmarking (#791), account pooling or rotation, API proxying, production rollout.
- Storing SIWC tokens in mctl-api, Vault, GitOps, GitHub Actions or any shared MCTL service.

## Additional acceptance — confirmed SIWC/Codex constraints (2026-11-22)

- WHEN local SIWC registration completes THE SYSTEM SHALL verify issued `client_id`, verified ID-token identity, the granted `chatgpt.tokens.use.direct` scope and account/workspace binding; an identity-only login SHALL NOT authorize inference. Reusing a credential for another MCTL user, host ID or workspace SHALL fail closed.
- WHEN the CLI launches a local Codex app-server it SHALL set the issued short-lived token only as **`ACCESS_TOKEN` in the isolated child environment**, with documented Responses `model_provider`/`env_key` settings and stdio JSON-RPC. The token SHALL NOT appear in command arguments, emitted config/logs, source-control files, persisted `CODEX_HOME`, subprocess snapshots collected by tests, or MCP tool payloads. Parent CLI owns refreshing. Re-start with new `ACCESS_TOKEN` and resume only the explicitly recorded local thread after refresh.
- WHEN choosing a Codex model, `model/list` SHALL be treated as a potentially bundled catalog, **not entitlement proof**. The result of a completed inference turn and the user's granted scopes are the relevant evidence; no global hard-coded plan access assertions.
- WHEN using SIWC Responses, SHALL honor `store:false`, `stream:true`, client-managed history and restrictions on unsupported `background`, `previous_response_id` for HTTP, hosted MCP/connectors and native computer tools. Codex's local shell/MCP/child-agent tools are a **separate execution plane** and must be disabled or mediated by MCTL policy; no automatic reuse of unrestricted Codex defaults.
- IF MCTL cannot technically constrain shell, MCP, child agent, filesystem and outbound actions to the approved execution/capability context, THEN the Codex path SHALL refuse the operation before starting a model turn, even if the SIWC token works. Include an explicit fake disallowed deploy-command, a revoked permission, a cross-tenant tool request and a credential-exfiltration attempt as negative tests.
- IF the plan quota is exhausted, app-specific limits apply, consent is revoked, or a paid-credit/overage route is offered, THEN the client SHALL report the relevant stable reason and stop; no silent billable fallback, user/account rotation or borrowed quota. Subscription allowances are shared as described in [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions) and shall never be advertised as independent free capacity.
- WHEN user disconnects, all child processes holding `ACCESS_TOKEN` SHALL terminate promptly. For a same-user self-hosted VM, record that [host-specific usage attribution and revocation are not yet available](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms); an individual host disconnect must not be falsely reported as server-confirmed revocation.
- WHEN documenting product eligibility, source-map open-source locally hosted personal use separately from paid/remote multi-tenant MCTL. For a paid or remotely hosted product, status remains `NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS` until OpenAI provides access. No existing ChatGPT web conversation wake/modify capability is implied.
- WHEN Gate 0 concludes DEFER/REJECT, T1–T13 and any live-only fixtures SHALL be marked `NOT_RUN_GATE0`/`UNMEASURED` with reason rather than failing nonexistent prototype code. G0 + policy + report lints remain mandatory.

## Open questions

- Registration/scopes have now been sourced from the official [SIWC sign-in page](https://developers.openai.com/siwc/token-sharing-open-source/sign-in): `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct` (the last scope grants plan use). Continue to verify model-discovery error semantics and revocation endpoints in their dedicated official pages; all unsourced deployment permissions remain `UNSOURCED`, not `ALLOWED`. Never infer background automation or cross-user usage permission from an OAuth grant.
- Should logout also forget the persisted `client_id` and `ext_agent_host_id`? The docs say re-sign-in does not create a new host, which argues for keeping them. This proposal keeps both by default and adds an explicit `--forget-client` flag. The owner may prefer otherwise.
- Codex app-server credential handoff is **documented**: the parent app owns the OAuth token; provide the access token only in the **ephemeral child-process environment variable `ACCESS_TOKEN`** with a configured Responses provider `env_key="ACCESS_TOKEN"`; run app-server with `--listen stdio://`. An OAuth refresh requires stopping/restarting the child with the new token and `thread/resume`. No JSON-RPC token handoff, token in argv, `~/.codex/auth.json` scraping or persisted child environment file. [Official Codex app-server SIWC doc, accessed 2026-11-22](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server). Actual MCTL tool-policy integration, process isolation, restart/resume and entitlement are **UNMEASURED** until fixtures/authorized pilot.
- The live dogfood run needs a human with a browser and an eligible plan. If no one runs it, every live field stays `UNMEASURED` and the decision must rest on the fake fixture plus the sourced policy.
- `cli/mctl` has no CI workflow in mctl-gitops `.github/workflows/`, and its Makefile stamps the version through `github.com/mctlhq/mctl-gitops/tools/mctl/cmd.version`, while the module path is `.../cli/mctl`. Both are noted as follow-up candidates. Neither blocks the spike.
