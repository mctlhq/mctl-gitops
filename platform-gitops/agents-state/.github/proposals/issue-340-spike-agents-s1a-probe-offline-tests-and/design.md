# Design: issue-340-spike-agents-s1a-probe-offline-tests-and

## Current state

Repository (clone of mctlhq/.github at `9efc051`, "Merge pull request #338"):

- `roadmap/spikes/agent-client-compatibility.yaml` declares the spike
  (`lifecycle: proposed`, outcomes `PLATFORM_READY | FIX_PROTOCOL_FIRST |
  AUTH_PATH_PER_AGENT | NOT_A_FIT`, `evidence.report:
  docs/spikes/agent-client-compatibility.md`). Nothing else in the repo
  references the spike yet: there is no `docs/spikes/agent-client-compatibility/`
  directory and no report. `python3 roadmap/scripts/validate.py roadmap/epics
  roadmap/spikes` passes today.
- Python spike precedents: `docs/spikes/cve-advisory-impact/` and
  `docs/spikes/finance-assistant/` each have a stdlib `model.py`, `fixtures/`
  and `tests/test_*.py`. Tests put the parent dir on `sys.path`
  (`sys.path.insert(0, ROOT); import model`) and are run with
  `python3 [-I] -m unittest discover -s <dir>/tests -v`.
- `.github/workflows/workflow-tests.yml` has `permissions: {}`, duplicated
  `paths:` lists under `pull_request` and `push`, and one unittest step per
  spike (the finance step uses `python3 -I`). No step has network needs beyond
  the pinned Temporal CLI download in the separate `temporal-dev-server` job.
- Report conventions (`docs/spikes/finance-assistant.md`,
  `docs/spikes/edge-config-kv-instant.md`): a non-claims section, explicit
  evidence tags, a pin table, "unknown (not observed) is never absent", and a
  proposed-not-decided verdict. `AGENTS.md` keeps a `# Spikes` index.
- Design reference: the expired #290 proposal at
  `platform-gitops/agents-state/.github/proposals/issue-290-spike-agents-which-coding-agents-can-con/`
  (design.md step-ladder table, fixtures list, `verdict()` precedence,
  tasks T1-T10). This slice keeps its tasks 1-4 and a reduced task 7, and
  drops tasks 5-6 (live run, hand checks) to #290.

Deployed state checked:

- `curl https://api.mctl.ai/.well-known/oauth-protected-resource/mcp`
  (2026-11-13): `resource=https://api.mctl.ai/mcp`,
  `authorization_servers=["https://api.mctl.ai"]`, `scopes_supported=["mctl"]`.
- `curl https://api.mctl.ai/.well-known/oauth-authorization-server`
  (2026-11-13): `registration_endpoint=https://api.mctl.ai/oauth/register`,
  `client_id_metadata_document_supported=true`,
  `code_challenge_methods_supported=["S256"]`,
  `grant_types_supported=["authorization_code","refresh_token"]`,
  `token_endpoint_auth_methods_supported=["none","private_key_jwt"]`,
  `revocation_endpoint`, `jwks_uri`. No device-code or client-credentials
  grant advertised. This is unchanged from the 2026-10-31 observation in the
  #290 proposal.
- Unauthenticated `POST https://api.mctl.ai/mcp` with an `initialize` body
  (2026-11-13): `HTTP/2 401`, `www-authenticate: Bearer
  realm="https://api.mctl.ai",
  resource_metadata="https://api.mctl.ai/.well-known/oauth-protected-resource/mcp"`.
  The response also sets an `mctl_api_affinity` cookie; the probe must not
  persist it.
- `$MCTL_GITOPS_ROOT/services/` holds only `admins`, `karabu`, `labs`,
  `namax66`; no `mctl-api` service directory, so mctl-api's deployed values
  (including DCR redirect URI policy) were not observed. This slice needs
  none of them.
- Not run: any `POST /oauth/register`, any authenticated call. These are
  operator steps on #290.

These observations are investigator evidence only; the draft report's
`[OBSERVED]` cells must come from the probe's own run with its commit hash,
not from these curl calls.

## Proposed solution

All changes are additive in mctlhq/.github under
`docs/spikes/agent-client-compatibility/`, plus one report, one CI step and
one `AGENTS.md` line. No service changes.

### 1. `agents.json` (profiles, data only)

A JSON object `{"schema": 1, "source": "https://developers.cloudflare.com/agent-setup/", "accessed": "<date>", "agents": [...]}`
with 12 entries in the issue's order. Each entry:

```
{
  "name": "Cursor",
  "doc_url": "<vendor MCP doc>",
  "version_documented": "unknown" | "<string>",
  "transport": {"value": "streamable-http" | "sse" | "stdio-only" | "unknown", "doc_url": "..."},
  "auth": {"value": "oauth-dcr" | "oauth-cimd" | "oauth-preregistered" | "static-header" | "device-code" | "none" | "unknown", "doc_url": "..."},
  "redirect_uri_form": {"value": "loopback" | "custom-scheme" | "hosted" | "unknown", "doc_url": "..."},
  "surfaces_prompts": {"value": true | false | "unknown", "doc_url": "..."},
  "runs_where": {"value": "local" | "cloud" | "unknown", "doc_url": "..."},
  "untested_reason": null | "<text>"
}
```

Every non-`unknown` value carries a `doc_url`. A loader check in `probe.py`
(`load_profiles()`) rejects a profile whose value is not `unknown` but lacks a
`doc_url`, or whose value is outside the enum. `auth: unknown` requires an
`untested_reason`, and such a row is rendered `UNTESTED`.

### 2. `probe.py` (stdlib only: `urllib.request`, `json`, `argparse`, `os`, `re`, `hashlib`, `secrets`, `base64`)

Step ladder (from the #290 design):

| Step | Action | Pass predicate |
| --- | --- | --- |
| 1a transport | POST JSON-RPC `initialize` per profile transport; `stdio-only` -> `n/a` | 401 with `WWW-Authenticate` containing `resource_metadata`, or 200 with a token |
| 1b discovery | GET protected-resource metadata (from `resource_metadata`), then AS metadata (RFC 8414 path) | fields required by profile auth present: `registration_endpoint` (DCR), `client_id_metadata_document_supported` (CIMD), matching grant (device-code/static) |
| 1c registration | DCR only, only with `--register`: POST client metadata with profile redirect form | 201 + `client_id`; otherwise `not run (--register off)` |
| 1d token | token from `MCTL_PROBE_TOKEN`; profile auth not supported by AS metadata fails without a request; `initialize` with bearer | 200 with `result.serverInfo` |
| 2 list | `tools/call mctl_list_platform_skills` | non-empty skills list |
| 3 read | `tools/call mctl_read_platform_skill` on first skill | non-empty body |
| 4 prompt (optional) | `prompts/list`, `prompts/get platform-skill` when profile surfaces prompts | prompt present with content |

Structure:

- `Step` result dataclass-like dicts: `{"step", "status": "pass"|"fail"|"not run (...)"|"n/a", "evidence": {...}}`.
- `run_profile(profile, endpoint, token, register, http)` where `http` is an
  injectable function (default `urllib`) so tests can count requests (for
  example, assert zero requests to `/oauth/register` without `--register`).
- Streamable HTTP responses: accept `application/json` and a single
  `text/event-stream` `data:` message.
- `redact(obj, token)` walks strings, replacing the token value, `Bearer \S+`,
  and JSON/query values for `access_token`, `refresh_token`, `client_secret`,
  `code`, `code_verifier` with `[REDACTED]`. All output passes through it.
- `mctl_change(failed_step, profile)` maps a failing step to a one-line
  "what mctl would have to change" (for example 1d with `device-code` ->
  "device authorization grant not advertised").
- `verdict(results) -> (outcome, rule)` is pure, with thresholds as module
  constants `PASS_READY=8`, `SAME_STEP_MAJORITY=7`, `AUTH_ONLY_MIN=3`,
  `NOT_A_FIT_BELOW=4` and precedence `PLATFORM_READY`, `FIX_PROTOCOL_FIRST`,
  `AUTH_PATH_PER_AGENT`, `NOT_A_FIT`, else `NO_RULE_MATCHED`. `UNTESTED` and
  `not run` count as not passing. The draft report does not call it.
- CLI: `--endpoint` (required), `--profiles` (default `agents.json` next to
  the script), `--only NAME`, `--register` (default off), `--markdown`,
  `--timeout`. No token flag. Exit 0 on a completed run regardless of step
  outcomes; non-zero only on usage/profile errors.
- Safety: no cookie jar, no write tools, HTTPS or loopback endpoints only
  (http allowed only for `127.0.0.1`/`localhost` so tests work).

### 3. Offline tests

`tests/fake_server.py` runs `http.server.ThreadingHTTPServer` on
`127.0.0.1:0` in a thread, with a `variant` selecting behaviour; base
metadata in `fixtures/as-metadata.json` and `fixtures/prm.json` mirrors the
observed api.mctl.ai shape. `tests/test_probe.py` covers:

- `good`: reference profile (streamable HTTP, `oauth-dcr`) with a test token
  reaches 3 and step 4 passes.
- `wrong_path`: 404 at `/mcp`, fails at 1a with the 404 verbatim.
- `bad_bearer`: 401 `invalid_token`, fails at 1d; token string absent from
  JSON and markdown output.
- `no_dcr`: DCR profile fails at 1b; CIMD profile passes 1b.
- `empty_skills`: fails at 2.
- `no_prompt`: 1-3 pass, step 4 fails.
- No token: 1d/2/3/4 are `not run (no token)` and the fake server records no
  `tools/call`.
- Without `--register`: zero requests to the registration path; with
  `--register` against the fake: 1c passes.
- `verdict()` matrices for each outcome, each precedence tie, and
  `NO_RULE_MATCHED`; `UNTESTED` counts as not passing.
- Redaction of each secret key and `Bearer` values.
- `load_profiles()` on the committed `agents.json`: 12 entries, names in
  order, every non-unknown value has `doc_url`, every `auth: unknown` has
  `untested_reason`; and on a malformed fixture it raises.

"Fails when the behaviour is removed" is satisfied by asserting the exact
`failed_step` and status strings rather than just truthiness, and by the
request-count assertions. The PR description records a manual mutation check
(each predicate forced to pass makes its red test fail).

### 4. CI

Add `'docs/spikes/agent-client-compatibility/**'` to both `paths:` lists in
`.github/workflows/workflow-tests.yml` and, in job `test`, a step:

```
- name: Agent-client compatibility probe offline tests (mctlhq/.github#290)
  run: python3 -I -m unittest discover -s docs/spikes/agent-client-compatibility/tests -v
```

`permissions: {}` unchanged; the fake server binds loopback only.

### 5. Draft report `docs/spikes/agent-client-compatibility.md`

Sections: status banner ("Draft, slice S1a of #290 (#340); verdict pending
live run (#290)"); non-claims; evidence tags (`[DOC]`, `[OBSERVED]` with date
and probe commit, `UNTESTED` with reason); pins; method (ladder table, probe
CLI, profiles); token-less discovery result from
`python3 probe.py --endpoint https://api.mctl.ai/mcp --markdown`, pasted with
date and commit; the 12-row matrix in the #290 column order (`agent | version
| transport | auth method supported | step reached | failing error verbatim |
what mctl would have to change`) plus a step-4 column; `Verdict: pending live
run (#290)` with no outcome proposed; operator steps remaining on #290.
Step-reached cells may say at most `1b [OBSERVED]` (or `1c metadata only`)
and `1d-3 UNTESTED: no token (operator step on #290)`.

`AGENTS.md` gets one `# Spikes` entry marked draft. The spike manifest is not
touched.

## Alternatives

- **Keep the full #290 scope in one DevLoop.** Dropped by the owner decision
  of 2026-11-13: the live run needs a human token, so the previous DevLoop
  expired unapproved. The narrowed slice can be completed and merged on its
  own.
- **Go probe with mcp-go, like `docs/spikes/mcp-gateway-g0/`.** Dropped: a
  library normalises client wire behaviour the probe exists to measure, and
  the issue mandates Python stdlib.
- **Use recorded HTTP fixtures (replay) instead of a live local fake
  server.** Dropped: a real loopback server exercises the probe's actual
  `urllib` path, header parsing and SSE handling, and lets tests count
  requests to prove `--register` and no-token gating.

## Platform impact

- No migrations, no service or gitops change, no new auth path. Additive docs,
  a script, tests and one CI step.
- CI cost: one extra unittest step of a few seconds, loopback only.
- Production load from the token-less run: about 3 requests per transport
  profile, all reads; no registration, no cookie persistence.
- Risk: a draft cell is read as a result. Mitigation: every cell tagged; the
  verdict section is fixed text; a test asserts the report contains
  `pending live run (#290)` and 12 matrix rows, and that no cell for steps
  1d-3 is tagged `[OBSERVED]`.
- Risk: profile drift or guessed fields. Mitigation: `doc_url` per field,
  `unknown` enforced by `load_profiles()`.
- Risk: secrets in output during the later live run. Mitigation: token only
  from env, redaction tested on JSON and markdown paths.
