# Design: issue-290-spike-agents-which-coding-agents-can-con

## Current state

Repository conventions (read in the clone of mctlhq/.github):

- The spike is already declared in `roadmap/spikes/agent-client-compatibility.yaml`
  (`kind: SpikeDefinition`, `lifecycle: proposed`, outcomes
  `PLATFORM_READY | FIX_PROTOCOL_FIRST | AUTH_PATH_PER_AGENT | NOT_A_FIT`,
  `execution.devloop: true`, `evidence.report:
  docs/spikes/agent-client-compatibility.md`). The schema
  `roadmap/schemas/spike-definition.schema.json` allows a `decision` block only
  when `lifecycle: decided`, so the report proposes a verdict and does not set
  one. This matches `docs/spikes/edge-config-kv-instant.md` ("Proposed verdict
  ... The owner has not recorded a decision").
- Spike reports live in `docs/spikes/<name>.md`, with reference code next to
  them in `docs/spikes/<name>/`. `docs/spikes/cve-advisory-impact/` is the
  Python precedent: `model.py` (stdlib only) plus `tests/test_*.py` plus
  `fixtures/`. `docs/spikes/mcp-gateway-g0/` is the Go precedent.
- `.github/workflows/workflow-tests.yml` runs each spike's offline tests on
  path filters (`docs/spikes/cve-advisory-impact/**` and so on) with
  `python3 -m unittest discover -s <dir>/tests -v` and `permissions: {}`.
- Reports use evidence tags (`[CODE]`, `[DEPLOYED]`, `[DOC]`) and a pin table,
  and they never read "unknown (not observed)" as absent
  (`docs/spikes/edge-config-kv-instant.md`, `docs/spikes/mcp-gateway-g0.md`).
- `AGENTS.md` has a `# Spikes` index that each new spike report is added to.
- `docs/plans/mcp-gateway.md` (table at line 76) records that `api.mctl.ai/mcp`
  runs its own OAuth 2.1 server (PKCE, DCR) with ZITADEL as the sign-in
  upstream, and also accepts ZITADEL JWTs via `MCTL_OIDC_PROVIDERS`.
  `docs/spikes/mcp-gateway-g0.md` lists the handlers involved
  (`internal/api/oauth_handlers.go:handleOAuthToken`, which accepts only
  `authorization_code` and `refresh_token`, and `handleProtectedResourceMeta`).

Deployed state checked:

- `curl https://api.mctl.ai/.well-known/oauth-protected-resource/mcp` returned
  `resource=https://api.mctl.ai/mcp`, `authorization_servers=[https://api.mctl.ai]`
  and `scopes_supported=[mctl]`. `[DEPLOYED]`
- `curl https://api.mctl.ai/.well-known/oauth-authorization-server` returned
  `registration_endpoint=/oauth/register` (DCR), `client_id_metadata_document_supported=true`
  (CIMD), `code_challenge_methods_supported=[S256]`,
  `grant_types_supported=[authorization_code, refresh_token]`,
  `token_endpoint_auth_methods_supported=[none, private_key_jwt]` and `jwks_uri`.
  It advertises no device-code grant and no client-credentials grant. `[DEPLOYED]`
- An unauthenticated `POST https://api.mctl.ai/mcp` returned `401` with
  `WWW-Authenticate: Bearer realm="https://api.mctl.ai",
  resource_metadata="https://api.mctl.ai/.well-known/oauth-protected-resource/mcp"`,
  which is the RFC 9728 discovery an MCP client follows. `[DEPLOYED]`
- `mctl_whoami` (this run's MCP connection) reported user
  `agent:issue-investigator`, not admin, no teams. `mctl_list_platform_skills`
  returned 3 public, active skills: `archify-diagrams`, `git-flow` and
  `mcp-troubleshooting`. Step 2 of the smoke test therefore works for a
  non-tenant identity. `[DEPLOYED]`
- `$MCTL_GITOPS_ROOT/services/` has no `mctl-api` service directory. Only
  `admins/mctl-support/values.yaml` references `MCTL_API_URL` and
  `MCTL_AUTH_ISSUER=https://api.mctl.ai`. Not observed: mctl-api's own deployed
  values, including its DCR redirect URI policy. It is not a tenant service in
  this tree.
- Not run: a DCR `POST /oauth/register`, `mctl_read_platform_skill` and
  `prompts/list`. Investigation is read-only, so the spike measures these.

## Proposed solution

The spike adds three artefacts to mctlhq/.github and changes no service.

### 1. Probe: `docs/spikes/agent-client-compatibility/probe.py`

The probe is written in Python and uses only the stdlib (`urllib`, `json`,
`hashlib`, `secrets`), following the `cve-advisory-impact/model.py` precedent.
It runs the smoke test as a fixed step ladder, and each step has one
pass/fail predicate:

| Step | What the probe does | Pass predicate |
| --- | --- | --- |
| 1a transport | POST `initialize` to the endpoint with the profile's transport (streamable HTTP; legacy SSE when the profile says so; `stdio-bridge` profiles are marked not-applicable) | `401` with `WWW-Authenticate` carrying `resource_metadata`, or `200` when a token is given |
| 1b discovery | Fetch protected-resource metadata, then AS metadata | required fields for the profile's auth method are present (`registration_endpoint` for DCR, `client_id_metadata_document_supported` for CIMD, a matching grant for device/static) |
| 1c registration | Only for DCR profiles and only when `--register` is set: register with the profile's redirect URI form | `201` with a `client_id`; the error body is recorded verbatim on failure |
| 1d token | Use `MCTL_PROBE_TOKEN` when set (obtained once by a human through the reference OAuth flow); a profile whose auth method is unsupported by AS metadata fails here without a request | `initialize` returns `200` with a `serverInfo` |
| 2 list | `tools/call mctl_list_platform_skills` | `count > 0` |
| 3 read | `tools/call mctl_read_platform_skill` on the first public skill | non-empty body |
| 4 prompt (optional) | `prompts/list` then `prompts/get platform-skill` when the profile surfaces prompts | prompt present with content |

Agent behaviour lives in data, not code:
`docs/spikes/agent-client-compatibility/agents.json` has one profile per agent
with `name`, `version_documented`, `doc_url` (the public guide followed),
`transport`, `auth` (one of `oauth-dcr`, `oauth-cimd`,
`oauth-preregistered`, `static-header`, `device-code`, `none`, `unknown`),
`redirect_uri_form`, `surfaces_prompts`, `runs_where` (`local` or `cloud`) and
`untested_reason`. A row with `auth: unknown` and an `untested_reason` becomes
`UNTESTED`. The probe never guesses a profile.

The output is a JSON result per profile (`step_reached`, `step4`,
`error_verbatim` with bearer and code values redacted, and `mctl_change`
derived from the failing step), plus `--markdown`, which renders the 12-row
table that is pasted into the report. `verdict(results)` is a pure function
that applies the issue's thresholds. It uses this precedence:
`PLATFORM_READY` (at least 8 pass steps 1-3), then `FIX_PROTOCOL_FIRST` (at
least 7 fail on the same mctl-side step), then `AUTH_PATH_PER_AGENT` (3 or
more fail only at 1b-1d with transport green), then `NOT_A_FIT` (fewer than 4
pass). If no rule matches, it returns `NO_RULE_MATCHED`. `UNTESTED` counts as
not passing.

Production safety: the probe defaults to discovery only. `--register` and a
token are explicit opt-ins. The probe never prints tokens, uses no write tools,
and the endpoint and the token come from flags and env vars only.

### 2. Red proof: `docs/spikes/agent-client-compatibility/tests/test_probe.py`

The tests start a local `http.server` fake in-process, with fixtures under
`fixtures/`, in these variants:

- `good`: mirrors the observed api.mctl.ai metadata and returns 3 skills. The
  reference profile reaches step 3.
- `wrong_path`: returns `404` on `/mcp`. The probe fails at 1a.
- `bad_bearer`: returns `401 invalid_token` for any token. The probe fails at 1d.
- `no_dcr`: the AS metadata has no `registration_endpoint`. A DCR profile
  fails at 1b, while a CIMD profile still passes 1b.
- `empty_skills`: `count: 0`. The probe fails at 2.
- `no_prompt`: step 4 fails while steps 1-3 stay green, which proves step 4 is
  recorded separately.

The tests also cover `verdict()` with synthetic matrices for each outcome and
for the precedence cases, and they cover redaction (no `Bearer ` value
survives in `error_verbatim`). These tests run offline in CI. The live green
proof against `api.mctl.ai` (with a token) and the live red proof (with
`--endpoint https://api.mctl.ai/mcpx` and `MCTL_PROBE_TOKEN=invalid`) are run
once by hand. Their redacted output is pasted into the report with the date
and the probe commit.

### 3. Report: `docs/spikes/agent-client-compatibility.md`

The report follows the edge-config and mcp-gateway-g0 shape: non-claims and
evidence tags, a pin table, observed deployed auth surface (above), the probe
method and red/green proof, the 12-row matrix plus step-4 column, a "real
client vs probe" table for Claude Code, Codex and Cursor, findings per failing
step with "what mctl would have to change", and the proposed verdict computed
by `verdict()` with the rule shown. It closes with re-run instructions and the
re-open triggers (mctl-api adds a grant, an agent ships OAuth).

### 4. Wiring

- `.github/workflows/workflow-tests.yml` adds
  `docs/spikes/agent-client-compatibility/**` to both path filters, plus one
  step `python3 -m unittest discover -s
  docs/spikes/agent-client-compatibility/tests -v`. It stays offline with
  `permissions: {}`.
- `AGENTS.md` adds a `# Spikes` entry.
- `roadmap/spikes/agent-client-compatibility.yaml` is not edited (the owner
  records the decision).

Hypothesis to test, not a result: the deployed auth surface is
OAuth-with-browser only, with DCR or CIMD, loopback or custom-scheme redirect,
and no device-code or client-credentials grant. Local IDE and terminal agents
that implement MCP OAuth should therefore pass. Cloud agents (Devin, the
cloud-side Copilot coding agent) and agents that only accept a static header
are expected to stop at 1b/1d. That pattern would point to
`AUTH_PATH_PER_AGENT`, but the verdict comes only from the measured matrix.

## Alternatives

- **Hand-test all twelve agents.** Dropped: this needs twelve licences, cannot
  be re-run in CI, and a hand pass cannot be distinguished from a lucky one.
  Hand runs stay as a cross-check for the three clients we have.
- **Write the probe in Go with mcp-go, like `mcp-gateway-g0/`.** Dropped: the
  probe must emulate several clients' wire behaviour (headers, redirect forms,
  transport choice). A raw stdlib HTTP client keeps each step explicit and
  avoids a library normalising away the very differences being measured.
  Python stdlib also matches the cve-advisory-impact test wiring.
- **Run the live probe as a scheduled CI job with a stored refresh token.**
  Deferred: a long-lived refresh token in CI secrets is effectively a static
  credential. Deciding whether that is acceptable belongs to the auth-path
  decision under the fail-closed rule, not to this spike. CI runs the offline
  red/green proof only.

## Platform impact

- No migrations, no service change, no new auth path. Documentation, a script
  and one CI step.
- Production load: a handful of requests per manual run. With `--register`,
  each DCR profile creates one OAuth client registration in mctl-api. Risk:
  orphaned registrations. Mitigation: register only for distinct redirect
  forms (at most about 5) and record the client IDs in the report so they can
  be revoked. Without `--register`, nothing is written.
- Credential risk: the token used for the live run belongs to a low-privilege
  tenant user. It is passed by env var, never logged, and redacted in output
  (this is tested).
- Risk: probe profiles drift from what the real agents do. Mitigation:
  `doc_url` and `version_documented` are recorded per row, the hand
  cross-check covers three clients, and any divergence is a finding against
  the probe.
- Risk: vendor docs for Pi, Vibe, Command Code and Bionic are thin. Mitigation:
  such rows are `UNTESTED` with a reason, never guessed.
