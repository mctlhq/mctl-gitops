# Design: issue-891-spike-auth-inference-evaluate-siwc-as-en

## Current state

### `cli/mctl` (mctlhq/mctl-gitops), read from the checkout at `/workdir/mctl-gitops/cli/mctl`

- Module `github.com/mctlhq/mctl-gitops/cli/mctl` (Go 1.26.9, cobra, `golang.org/x/oauth2`, `coreos/go-oidc/v3`). Commands are registered in `cmd/root.go`: `deploy`, `delete`, `config`, `auth`, `repo`, `status`, `logs`, `version`.
- `cmd/auth.go`: `mctl auth login|status|logout`. Login has one alternative credential, selected with a flag (`--zitadel`, plus `--no-browser`), and logout mirrors it (`logout --zitadel`). `authStatus` reports the credential that `GetToken` would send (`MCTL_TOKEN` > `MCTL_AUTH` > stored sign-in) and confirms it through `/api/v1/whoami` (`whoami{ID, Groups, IsAdmin}`). `warnNoAccess` already handles a non-admin user with no groups.
- `internal/auth/api.go`, the default MCTL sign-in. It runs RFC 8414 discovery (`discoverAPI`, which requires every endpoint to be on the API origin and S256 to be offered), RFC 7591 dynamic registration per login (`registerAPIClient`, public client, `token_endpoint_auth_method: none`), and a loopback `127.0.0.1:0` redirect. It refuses tokens that carry no refresh token or no expiry. Credentials go to `storedAPIToken{APIURL, ClientID, Token}` in `<UserConfigDir>/mctl/api-token.json` (`MCTL_API_TOKEN_FILE`), and a credential is never sent to a different API. `refreshAPIToken` rotates under `lockTokenFile`. `APILogout` revokes the refresh token at the RFC 7009 endpoint and deletes the file even if revocation fails, returning `revokeErr`.
- `internal/auth/zitadel.go` provides the reusable primitives. `writeOwnerOnly` writes mode 600 through temp file and rename. `lockTokenFile` uses an O_EXCL `.lock` and an owner nonce, waits 45 s, and takes over a stale lock after 5 min by rename. `awaitLoopbackCode` and `callbackResult` compare state in constant time and refuse a "foreign" callback without ending the login. Nonce verification is shown in `ZitadelLogin`; there are also `randomToken` and `launchBrowser`. The file comments state the rule that matters for SIWC: rotating refresh tokens must never be presented twice.
- `internal/auth/gh.go` is the deprecated `MCTL_AUTH=github` path. `internal/vault/client.go` exists but is unrelated to user inference.
- There is no OS-keychain integration. Every credential is a 0600 JSON file under the user config directory.
- Distribution is build-from-source (`make install`, README "Install"). No mctl-gitops workflow under `.github/workflows/` builds or tests `cli/mctl`.
- These packages are under `internal/`, so code outside the module cannot import them. An experiment in another repo must copy the patterns, and the report records that copy as delta.

### mctl-agents (this repo)

- The #824 provider seam is `config/model_policy.py`, documented in `docs/model-policy-providers.md`. A profile's `provider` block accepts only `api: anthropic-messages` (`model_policy.py` line ~108). `provider_session_env` turns it into `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` for the Claude Agent SDK child, and `credential_env` names a server-side env var. An OpenAI Responses credential that the user holds locally does not fit this seam: it is the wrong wire protocol, and the credential sits in the worker env.
- #746 (`docs/spikes/746-portable-runtime.md`, `experiments/portable-runtime-rs/`, `baseline/thin_adapter.py`) concluded `THIN_ADAPTER`: a stdio-to-Streamable-HTTP `/mcp` proxy with an allowlist (`tools/list` filtered, a non-allowlisted call refused as `not-eligible`), 0600 token-file handling and an `init` config generator. It is an MCP bridge, not an inference runtime.
- #791 (`docs/spikes/791-hetzner-inference.md`, `docs/spikes/791/fixtures/{investigation,implementation,review,tool-use}/fixture.yaml`) provides the bounded fixture format: `oracle.expect`, `required_tools`, `disallowed_tools`, `limits`. `tool-use` already contains a "tempting disallowed tool" (`mcp__mctl__mctl_deploy_service`), which is exactly the governance check SIWC needs.
- Spike conventions: reports in `docs/spikes/<n>-<slug>.md` with a `## Decision` holding one token, experiments in `experiments/<name>/`, manual or no-secret workflows like `.github/workflows/spike-881-sandbox.yml` and `portable-runtime-spike.yml`. `orchestrator/spike_issue.py` makes the implementer emit `Refs`, not `Closes`, for `spike(` titles.
- `orchestrator/redaction.py` already redacts `sk-` keys. It has no rule for ChatGPT OAuth JWT access tokens.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`: `MODEL_PROVIDER: nebius`, `NEBIUS_MODEL: zai-org/GLM-5.1`, with a model credential from Vault `secret/data/platform/mctl-support/model`. mctl-support is shared hosted infrastructure in tenant `admins` on a provider key, so it is matrix shape 8.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the worker authenticates the Claude Agent SDK with `CLAUDE_CODE_OAUTH_TOKEN` from an ExternalSecret, so the DevLoop runs in the shared `admins` cluster. Any SIWC grant used there would be matrix shape 6 or 7, not a user-controlled runtime.
- `$MCTL_GITOPS_ROOT/services/` lists tenants `admins`, `karabu`, `labs` and `namax66`. No service references OpenAI or ChatGPT credentials. This was checked by grep over the mctl-support and mctl-agents-worker values only, not every service.
- `/workdir/mctl-gitops/.github/workflows/`: no workflow references `cli/mctl`.
- The mctl MCP tools were not called. The gitops files above were enough for this proposal, and no runtime state of the CLI exists on the platform.
- The SIWC source page (https://developers.openai.com/siwc/token-sharing-open-source, read 2026-10-29) says:
  - It covers "open-source and locally hosted apps".
  - Each `client_id` is bound to one user and workspace.
  - Several hosts (a laptop, a self-hosted VM) may share a `client_id`, each with its own opaque `ext_agent_host_id` (JWK thumbprint URI recommended).
  - Re-sign-in does not create a new host.
  - Paid or remotely hosted offerings need the interest form.
  - Responses calls use bearer, `store: false`, `stream: true`.
  - It does not state scope names, the model-discovery endpoint, revocation, or the rules on another user's activity, proxying, pooling or background automation. Those are open questions.

## Proposed solution

The deliverable is a spike: evidence, an isolated experiment, a fake-auth CI fixture and one recommendation. Nothing ships to `cli/mctl` or to the workers in this change.

### 1. Experiment: `experiments/siwc-cli-891/` (Go module, mirrors `cli/mctl`)

It is written in Go so the measured delta transfers one-to-one to `cli/mctl`. Package layout:

- `internal/siwcauth/`
  - `hostid.go`: creates and persists an opaque `ext_agent_host_id` (JWK thumbprint URI of a locally generated Ed25519 key, or UUIDv4 URN as fallback) in `<UserConfigDir>/mctl/openai-host-id.json`, mode 600. The ID never contains user-identifying data.
  - `login.go`: SIWC discovery, then dynamic client registration (only when no `client_id` is stored), then a loopback `127.0.0.1:0` authorization-code flow with PKCE S256, state and nonce. `awaitLoopbackCode`, `callbackResult`, `randomToken` and `launchBrowser` are copied verbatim from `cli/mctl/internal/auth/zitadel.go`, with a header citing the source commit. The ID token is verified and the granted scopes are checked for plan usage before anything is written.
  - `store.go`: `storedSIWC{Issuer, ClientID, HostID, AccountID, Workspace, Token}` in `<UserConfigDir>/mctl/openai-siwc.json` (`MCTL_OPENAI_SIWC_FILE`), through a copied `writeOwnerOnly`. The file is separate from `api-token.json`, so the existing `GetToken` order is unchanged.
  - `refresh.go`: `Token()` and `refresh()` under a copied `lockTokenFile`. After taking the lock it re-reads the file, the same double-check as `refreshAPIToken`.
  - `logout.go`: deletes tokens and attempts revocation if a documented endpoint exists, returning `revokeErr` in the same shape as `APILogout`. It keeps `client_id` and `host-id` unless `--forget-client` is given.
- `internal/openai/`
  - `models.go`: account-specific model discovery. Reason codes: `ok`, `not-eligible`, `empty-catalog`, `model-unavailable`, `rate-limited`, `usage-limit`, `auth-expired`, `auth-revoked`.
  - `responses.go`: streaming Responses client (`store: false`, `stream: true`, consumed to `response.completed`). It keeps conversation history on the client, so nothing depends on server-side storage.
  - `tools.go`: a local tool loop. Model-proposed function calls run only if they appear in an allowlist loaded from the fixture's `required_tools`. A call listed in `disallowed_tools`, or any other unknown call, gets `not-eligible` back without running, using the same vocabulary as #746. This is where MCTL policy stays authoritative.
- `cmd/siwc-spike/`: a cobra binary whose command tree matches the proposed CLI UX, so UX and step counts are measured and not guessed:
  - `siwc-spike auth openai login [--no-browser]`
  - `siwc-spike auth openai status`
  - `siwc-spike auth openai logout [--forget-client]`
  - `siwc-spike auth status`: two sections, "MCTL identity" (the fake `whoami`) and "Inference identity (OpenAI/ChatGPT)" (account, workspace, host ID suffix, expiry, entitlement). It never shows a token.
  - `siwc-spike models --provider openai`
  - `siwc-spike run --fixture <path> [--engine responses|codex]`
- `internal/codexbridge/`, for option E. It launches `codex app-server` as a child with stdio JSON-RPC, gives it a scratch `CODEX_HOME`, and hands over the access token only over the JSON-RPC channel (never argv, env file or `auth.json`). It records whether app-server accepts external tokens at all, then refresh behaviour, thread/resume, and whether shell, MCP and child-agent capabilities can be narrowed to the fixture allowlist. If the handoff needs Codex's own login or a persisted `auth.json`, the result is `CODEX_OWNS_CREDENTIAL` and option 2 fails invariants 4 and 5. Live only. In CI it is a skipped test with a reason.
- `testdata/fake/`: in-process fakes started by `httptest`.
  - Fake SIWC authorization server: discovery, registration, authorize, token with rotating refresh tokens and reuse detection (a reused refresh token revokes the family), revocation, plus an ID token signed with a test key.
  - Fake model catalog with switchable variants: eligible, empty, model removed.
  - Fake Responses SSE stream: plain answer, function call, 429 rate limit, usage-limit, 401 expired, 401 revoked.
  - Fake MCTL `whoami` returning `{isAdmin:false, groups:[]}`.

### 2. Fixture

`docs/spikes/891/fixtures/` copies the #791 `investigation` and `tool-use` fixture format (same keys, new `id`s, sha256 recomputed) and adds `multi-turn/fixture.yaml`. Only the methodology is reused. No model-quality claims are made.

### 3. CI: `.github/workflows/spike-891-siwc.yml`

It triggers on `pull_request` for paths `experiments/siwc-cli-891/**` and on `workflow_dispatch`. It runs `go vet` and `go test -race ./...` against the fakes, with `permissions: contents: read`, `persist-credentials: false`, no secrets and no artifact upload. A final step greps the test log for JWT- or refresh-token-shaped strings and fails if it finds one.

### 4. Live owner dogfood (manual, local, not CI)

`experiments/siwc-cli-891/LIVE.md` documents a run on the owner's laptop. Only safe metadata goes into `docs/spikes/891/measurements/live-owner.json`: model IDs, counts, latencies, reason codes, RSS, step counts and the delta of the plan quota indicator if one is exposed. The JSON schema has no field that could hold a token or an email. Every live-only result is labelled `owner-dogfood-only`.

### 5. Report: `docs/spikes/891-siwc-byos.md`

Sections:
1. Current-state map (above, refreshed at the implementation SHA).
2. End-user journey with a step count. The expected count is 4 steps from a logged-in CLI: run `auth openai login`, press "Continue with ChatGPT", run `models`, run the operation. The spike measures it.
3. Policy matrix (10 shapes).
4. Measurements table (every metric in the issue; `UNMEASURED` where needed).
5. Option comparison (options 1 to 4).
6. Use-case scoring (7 use cases).
7. Credential lifecycle and storage recommendation.
8. Integration points.
9. Follow-ups.
10. `## Decision`.

Provisional policy matrix, to be confirmed against the linked SIWC pages during the spike:

| # | Shape | Provisional class | Basis |
|---|---|---|---|
| 1 | User laptop, `mctl` CLI, own account | ALLOWED | "locally hosted apps", per-user `client_id` |
| 2 | User laptop, CLI launches local Codex app-server | ALLOWED (credential-handoff caveat) | same runtime and user |
| 3 | User laptop, #746 adapter | ALLOWED | same runtime and user |
| 4 | User-controlled self-hosted VM | ALLOWED | source names self-hosted VM with own host ID |
| 5 | Owner, same generic flow | ALLOWED | identical to 1 |
| 6 | Owner grant consumed by remote DevLoop cluster (`admins` workers) | NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS | "remotely hosted" requires interest form |
| 7 | Shared MCTL SaaS / tenant runtime | NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS | same |
| 8 | mctl-support | NOT_ALLOWED | one tenant's action would consume another account's plan (invariant 7); `UNSOURCED` until OpenAI rule found |
| 9 | Paid MCTL tiers exposing SIWC | NEEDS_OPENAI_HOSTED/COMMERCIAL_ACCESS | "paid ... app" requires interest form |
| 10 | User-authorized background automation | NOT_ALLOWED until sourced | conservative default (requirements: unsourced is never ALLOWED) |

Consequences for integration points, also provisional:
- SIWC stays local to the CLI. Proposed follow-up packages in `cli/mctl`: `internal/openai/siwc` and `internal/openai/responses`, plus `cmd/auth_openai.go` and `cmd/models.go`.
- The #824 seam (`config/model_policy.py`) is not extended. A Responses provider there would put a user credential into the shared worker env (shapes 6 and 7).
- Personal DevLoop (use case 2) runs on the user's host and calls governed MCTL tools through the existing API token. It does not run through mctl-agents workers.
- mctl-support stays on its provider key.
- The decision rules in the issue are applied exactly as written, and the token is chosen from measurements. The spike predetermines no outcome.

### Proposed CLI UX, recorded in the report and to be confirmed

- The command group is `mctl auth openai login|status|logout`, not `mctl auth login --openai`. The existing `--zitadel` flag picks an alternative credential for the same purpose (calling mctl-api). SIWC is a different identity with a different purpose (inference), and a subcommand namespace keeps `mctl auth logout` from ever touching the ChatGPT grant, and the other way round.
- `mctl auth status` gains a second section. Its exit code still reflects only the MCTL sign-in, so existing scripts do not break.
- `mctl models --provider openai` takes the catalog from the user's grant only.
- Storage is a 0600 file under the same directory, with the same lock pattern. OS-keychain work is recommended as a follow-up only if the spike shows that the rotating SIWC refresh token needs stronger protection than the existing MCTL refresh token already has. Both are long-lived rotating credentials of the same class today.

## Alternatives

1. Put the proof directly in `mctlhq/mctl-gitops/cli/mctl` behind a hidden command. Dropped for the spike: it changes a user-facing binary before the owner records a verdict, against "no production rollout" and `Refs` not `Closes`. It also crosses into a repo whose CLI has no CI. The experiment copies `internal/auth` patterns and the report states the exact delta for a follow-up PR.
2. Route SIWC through the #824 provider seam (`api: openai-responses` in `config/model_policy.py`). Dropped. The seam injects a server-side `credential_env` into Claude Agent SDK children running in shared `admins` workers. That is shapes 6 and 7, and the credential would leave the user's control (invariant 6). It would also need a Responses-to-Messages protocol shim.
3. Build the experiment in Python next to the #746 baseline, or start from the thin adapter. Dropped. The target integration surface is the Go CLI, a Python proof would not measure the real delta, and #746 is an MCP bridge with no proven inference job. It is reused only if section F proves a need, otherwise `NO_ADAPTER_NEEDED_FOR_SIWC`.
4. Reuse Codex's own login (`~/.codex/auth.json`). Rejected by invariant 4.

## Platform impact

- Migrations and backward compatibility: none. The change adds new files under `experiments/siwc-cli-891/`, `docs/spikes/891*` and one opt-in workflow. No worker, profile, chart or `cli/mctl` change.
- Resources: CI only. A Go test job of about 1 to 2 minutes on `ubuntu-latest`, triggered by path. No cluster resources.
- Risks and mitigations:
  - Token leak through logs or artifacts. The fakes issue tokens with a recognisable prefix, a CI grep step fails on any token-shaped output, no artifact is uploaded, and the live JSON schema has no token field. Live runs are local only.
  - Inference running outside policy. The tool loop executes only allowlisted tools, and the `tool-use` fixture's disallowed `mctl_deploy_service` must come back `not-eligible`.
  - Policy misread. Unsourced rules default conservatively. The verdict stays with the owner.
  - Owner-specific shortcuts. A test asserts that the flow succeeds against a non-admin fake `whoami`, and a source grep test asserts there is no `isAdmin`/owner branching in `experiments/siwc-cli-891/`.
  - Drift from `cli/mctl` patterns. Copied functions carry their source path and commit, so the follow-up PR can diff them.
