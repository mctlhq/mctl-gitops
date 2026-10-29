# Spike: evaluate a portable single-binary MCTL agent runtime (Rust proof + decision)

## Context

Issue mctlhq/mctl-agents#746 asks for a time-boxed spike to decide two things with
code and measurements, not architecture preference. First, does MCTL need a small
agent-side process installed next to an external agent host (Claude Code, Cursor,
OpenClaw, a generic MCP host)? Second, if it does, is a Rust single binary materially
better than a thin adapter in an existing language, or than direct MCP? The spike ends
with exactly one recommendation: `NO_RUNTIME`, `THIN_ADAPTER`, `PORTABLE_RUNTIME_RUST`
or `PORTABLE_RUNTIME_OTHER`, applied against the GO criteria in the issue.

This matters because MCTL's control-plane primitives already live in this repository.
These include capability discovery and the gateway (`orchestrator/capability.py`,
`orchestrator/capability_gateway.py`, ADR 017), the policy checkpoint
(`orchestrator/policy_checkpoint.py`, ADR 014), execution identity (ADR 011), and
commerce (`orchestrator/commerce_gateway.py`, ADR 020). The credential-isolation lesson
of #717 is in `orchestrator/options.py::agent_env_without_mctl_token`. All of these
assume a hosted execution path. The spike measures whether a local data-plane boundary
adds value without becoming a second authorization authority, a second workflow engine,
or a second copy of business logic. Everything is built under an isolated
`experiments/portable-runtime-rs/` directory and is off by default.

## User stories

- AS a platform maintainer I WANT a measured, evidence-backed decision on whether to ship an agent-side runtime SO THAT we neither add a shipped component nor rule it out on preference alone.
- AS an external agent-host user I WANT one command that prints a working MCP config for my host SO THAT I do not hand-assemble MCP JSON, while my real host config stays untouched during the spike.
- AS a security reviewer I WANT proof that the runtime never puts the bearer token in argv, generated config or child processes SO THAT a local runtime does not weaken the #717 credential boundary.
- AS a policy owner I WANT proof that a remote DENY / REQUIRE_APPROVAL / error result passes through unchanged SO THAT local preflight can never turn into a grant.
- AS an operator I WANT each proxied call correlated from host request to runtime invocation id to upstream request id to outcome, using only hashes and ids SO THAT I can trace a call without the runtime keeping a shadow audit store.
- AS the implementer of a future follow-up I WANT a comparison matrix, a commerce/x402 boundary note and an ownership recommendation SO THAT any GO follow-up is narrowly scoped.

## Acceptance criteria (EARS)

### Isolation and default-off
- WHILE the experiment exists THE SYSTEM SHALL keep all runtime source, fixtures, harness and Cargo files under `experiments/portable-runtime-rs/`, and SHALL NOT reference them from `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh`, `pyproject.toml` or `uv.lock`.
- WHEN the production image is built THE SYSTEM SHALL contain no file from `experiments/`.
- WHEN `experiments/portable-runtime-rs/` (plus its optional CI workflow and isolation test) is deleted THE SYSTEM SHALL keep every existing test, lint and docker-smoke job of `.github/workflows/pr-validation.yml` passing unchanged.
- THE SYSTEM SHALL NOT modify any mctl-gitops manifest, create a repository, or enable production traffic.

### Executable surface
- WHEN `mctl-runtime doctor` runs THE SYSTEM SHALL report the binary version, the credential source in use (named only, never its value), upstream reachability, and the allowlist size. It SHALL exit non-zero on any failed check.
- WHEN `mctl-runtime init --host fixture` runs, with or without `--dry-run`, THE SYSTEM SHALL print the generated host MCP config to stdout and SHALL NOT write any file.
- IF `init` is given `--write --config-dir <dir>` THEN THE SYSTEM SHALL write only inside `<dir>`, and SHALL refuse unless `<dir>` is an explicitly supplied directory inside a test-created temporary root containing a fixture marker; canonicalize both paths, require the target to remain below that root, and reject symlinks escaping it. A caller-supplied arbitrary directory or a denylist of known host paths is insufficient. It SHALL never default to a real host config path.
- WHEN `mctl-runtime proxy` runs THE SYSTEM SHALL serve MCP over stdio to the host and forward allowlisted calls to one configured upstream over MCP streamable HTTP.

### J2 bridge semantics
- WHEN the host calls `tools/list` THE SYSTEM SHALL return only the intersection of the upstream tool list and the configured allowlist, with each tool's `name` and `inputSchema` identical to the upstream ones.
- IF the host calls a tool not on the allowlist THEN THE SYSTEM SHALL return an MCP error result (`isError: true`, reason code `not-eligible`) without contacting the upstream.
- IF the allowlist file is missing, empty or unparsable THEN THE SYSTEM SHALL refuse to start `proxy` (fail closed).
- WHEN the upstream returns a result with `isError: true` THE SYSTEM SHALL return it to the host with `isError: true` and the content unchanged.
- WHEN the upstream returns a DENY, REQUIRE_APPROVAL or refusal result for a tool the local allowlist permits THE SYSTEM SHALL return that refusal, never a success.
- THE SYSTEM SHALL NOT implement any Telegram, deployment, approval, ledger or other business logic locally.

### J3 credentials
- THE SYSTEM SHALL read the bearer credential only from a protected token file (`MCTL_RUNTIME_TOKEN_FILE`) or an environment variable (`MCTL_TOKEN`), and never from a command-line argument.
- IF the token file's permissions allow group or other read THEN THE SYSTEM SHALL refuse to use it and SHALL say why.
- WHEN `init` generates a host config THE SYSTEM SHALL reference the credential by env-var name or file path only, never by value.
- WHEN the runtime spawns any child process THE SYSTEM SHALL remove `MCTL_TOKEN` and `MCTL_RUNTIME_TOKEN_FILE` from the child's environment, and SHALL NOT pass the token in the child's argv.
- IF the token is absent THEN `doctor` SHALL fail with a "credential absent" diagnostic and `proxy` SHALL answer every `tools/call` with an error result. In neither case SHALL the runtime attempt an unauthenticated upstream call.
- WHEN the upstream answers HTTP 401 or 403 THE SYSTEM SHALL return an error result naming an expired or rejected credential, and SHALL NOT retry with any other credential.

### J4 policy preflight
- WHILE preflight is enabled THE SYSTEM SHALL only narrow: it may refuse locally, and it SHALL NOT synthesise a success or skip the upstream call for an allowed tool.

### J5 correlation
- WHEN a proxied call completes THE SYSTEM SHALL emit one structured stderr line with: `invocation_id`, the host JSON-RPC request id, tool name, the SHA-256 of the canonical arguments, the upstream request id when present and a SHA-256 hash of the upstream session id (never the raw session id), outcome, `is_error`, and latency.
- THE SYSTEM SHALL send `X-Mctl-Invocation-Id` upstream on each forwarded call.
- THE SYSTEM SHALL NOT persist arguments or results, and SHALL NOT create any local database or on-disk audit file.

### Failure behaviour
- IF the upstream is unreachable or times out THEN THE SYSTEM SHALL return an error result with reason code `provider-unavailable` or `provider-timeout` within a bounded timeout, and SHALL NOT crash the stdio session.

### Measurements and decision
- WHEN the measurement harness runs THE SYSTEM SHALL record these measurements in `docs/spikes/746-portable-runtime.md`:
  - release binary size;
  - cold start to ready;
  - idle RSS, and RSS during one proxied call;
  - proxy latency overhead on the first call and at steady state;
  - build time;
  - the result of each cross-build (Linux amd64, Linux arm64, macOS arm64; failures recorded as failures);
  - the count of runtime files and dependencies on the target host.

  It SHALL record the same available dimensions for a thin Python baseline adapter and for direct MCP.
- THE SYSTEM SHALL produce exactly one final recommendation in that report, justified against every GO criterion of the issue. Follow-up issue drafts SHALL be included only for confirmed GO gaps.
- THE REPORT SHALL explicitly evaluate whether model-provider routing, fallback, BYOK and provider abstraction belong outside a portable runtime and should instead remain in a model control plane such as Cloudflare AI Gateway / `createAI`. It SHALL cross-reference `mctlhq/.github#184` G4 rather than implementing model routing in this spike.

## External architecture evidence added before approval

### Cloudflare `createAI` / AI Gateway (2026-10-21)

Treat Cloudflare `createAI` as a boundary benchmark, not a selected dependency. Cloudflare now exposes Workers AI, AI Gateway catalog models, dynamic routes, provider-native model objects, fallback/retries, BYOK and related gateway behavior behind one model-access surface. The spike must therefore answer whether putting model routing/fallback/BYOK/provider abstraction into `mctl-runtime` would create an unnecessary second control-plane responsibility. Unless the experiment proves a concrete local model-routing job, keep #746 focused on host bootstrap, MCP/capability bridging, credential isolation, refusal UX and evidence correlation.

Production adoption of Cloudflare `createAI` / AI Gateway is out of scope. Any model-routing product finding belongs with `mctlhq/.github#184` G4.

Source: https://developers.cloudflare.com/changelog/post/2026-10-21-createai/

### Cloudflare MCP `/sse` retirement (2026-10-22)

Cloudflare's product-specific MCP servers now serve `/mcp` only; `/sse` returns `410 Gone`. This does **not** add a new implementation requirement because this proposal already uses stdio on the host-facing side and MCP Streamable HTTP on the upstream side. Do not add legacy `/sse` support or compatibility code to the spike.

Source: https://developers.cloudflare.com/changelog/post/2026-10-22-cloudflare-mcp-servers-retire-sse/

## Out of scope

- A new repository, package release, auto-updater or production deployment.
- Changes to mctl-gitops, mctl-api, mctl-telegram or any other repository.
- Wallets, payment keys, mainnet, live funds or production x402. J6 is a design note only.
- Local LLM inference, Android or edge runtime work (`.github#34`, `#652`).
- A local authorization or policy engine, a local evidence or audit database, and caching of private Telegram content.
- Writing to real user host configuration.
- OS keychain integration and loopback credential handoff beyond an interface sketch and design evaluation.
- Rewriting any existing service in Rust, or replacing MCP with another protocol.
- Supporting more than the `fixture` host plus, optionally, one real host shape (Claude Code) for printed config.
- Implementing model-provider routing, fallback, BYOK or Cloudflare `createAI` integration inside `mctl-runtime`.
- Supporting legacy MCP SSE transport solely for compatibility with retired `/sse` endpoints.

## Open questions

- The upstream request or execution id the runtime should correlate on is unknown. I could not observe whether `api.mctl.ai/mcp` returns a per-request id header. The spike correlates on a SHA-256 hash of `Mcp-Session-Id` plus any `X-Request-Id` the upstream returns, and records the gap if neither identifies a request.
- Rust MCP library: `rmcp` (the official Rust SDK) versus a hand-rolled JSON-RPC subset. The proposal prefers `rmcp` pinned at an exact version and falls back to a minimal hand-rolled subset if `rmcp` cannot do stdio-to-streamable-HTTP passthrough at that version. The report records which was used and why.
- macOS arm64 cross-build needs either a macOS runner or an SDK on Linux. The optional CI workflow uses a `macos-14` runner. If that is not permitted, the macOS result is recorded as "not measured", never as success.
- The baseline language for the thin adapter: Python is assumed, because the `mcp==1.29.0` SDK is already pinned in `uv.lock`. A Node baseline is not built, and only ecosystem evidence is cited for it.
- `experiments/` is not in the commit-lint non-shipping allowlist (`SHIPPING_PATHS='^(tests/|docs/|\.github/)'` in `pr-validation.yml`). The proposal adds `experiments/` to that allowlist, because nothing under it ships in the image. A reviewer may prefer a `feat` commit instead.
