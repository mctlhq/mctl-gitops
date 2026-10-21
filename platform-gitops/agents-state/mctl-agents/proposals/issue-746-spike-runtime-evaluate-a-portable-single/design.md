# Design: issue-746-spike-runtime-evaluate-a-portable-single

## Current state

### How an external host reaches MCTL today (direct MCP)

- MCTL exposes a remote MCP server at `https://api.mctl.ai/mcp`. Inside this repo it is
  wired by `orchestrator/options.py::mctl_mcp_config()`, which builds an HTTP MCP server
  entry. That entry carries `Authorization: Bearer $MCTL_TOKEN` and the execution-identity
  headers from `_execution_context_headers()` (`X-Mctl-Execution-Context`,
  `X-Mctl-Trace-Id`; ADR 011). When `MCTL_TOKEN` is unset, the function returns `{}` with a
  warning.
- External hosts (Claude Code, Cursor and others) connect to the same endpoint through
  their own remote-MCP and OAuth support. The `mctl_whoami` tool's own description says
  authentication "is handled automatically by the MCP connector's OAuth flow". For hosts
  with remote MCP and OAuth, the direct path already exists and needs no local process.
- The friction points a runtime could address, as the starting hypotheses the spike must
  confirm or reject:
  1. Hosts without remote-HTTP MCP or OAuth support need a stdio shim.
  2. Hand-assembling MCP JSON per host.
  3. Static-token users have to put a bearer token somewhere. Today that means
     host config, or an env var the host passes to every child.
  4. Refusal output from a remote DENY or REQUIRE_APPROVAL is plain text with no local
     diagnostics.
  5. There is no host-side correlation id.

### What already exists here and must not be duplicated

- **#242 / ADR 017.** `orchestrator/capability_gateway.py` is the capability runtime.
  `resolve_eligible()` seals a `CapabilitySet`, and `CapabilityGateway` serves
  `capability_search`, `capability_describe` and `capability_invoke`. Its invariants are the
  ones the spike must mirror at the local boundary:
  - discovery narrows and never grants: `_first_matching_pattern` returns `None` for
    anything outside `plan.tools`;
  - anything outside the sealed set is refused with `not-eligible` before any provider
    call;
  - `_McpProviderSession` preserves the provider's `isError` (line ~287:
    `ToolCallResult(is_error=bool(result.isError), ...)`), and the gateway maps it to
    reason code `provider-error`;
  - `ProviderUnavailableError` and `ProviderTimeoutError` map to
    `provider-unavailable` and `provider-timeout`;
  - `_correlation_headers()` sends correlation as tracing metadata only, never as an
    authorization claim.

  The spike reuses this vocabulary (ADR 017 section 7) rather than inventing a new one.
  It does not reimplement discovery or search.
- **#717.** `orchestrator/options.py::agent_env_without_mctl_token()` and `_scrubbed()`
  blank `MCTL_TOKEN` in every SDK session env, so tool subprocesses cannot call mctl-api
  past the in-process policy checkpoint. `tests/test_tool_subprocess_env.py` proves this by
  spawning a stub CLI whose shell child records what it sees. The spike's
  no-token-in-child test copies that pattern: a stub child records its argv and env, and
  the test asserts the token value is absent.
- **#197 / ADR 014.** `orchestrator/policy_checkpoint.py` (`evaluate`, `decide`,
  `enforce`, `PolicyRefused`) is the in-process policy authority for hosted agents. The
  local runtime does not embed it. Server-side policy stays authoritative, and the runtime
  is advisory only (an allowlist).
- **Commerce (ADR 020).** `orchestrator/commerce_gateway.py` and `orchestrator/commerce.py`
  hold dispatch-authorization verification (Ed25519 via `cryptography`). The x402 pilot is
  `mctl-api#616`. J6 stays a design note that points at these. No payment code is added.
- **Spike conventions.** Earlier spikes write a report at
  `docs/spikes/<issue>-<slug>.md`, plus artefacts in `docs/spikes/<issue>/`, plus a
  pinning test in `tests/`. Examples: `docs/spikes/661-canonical-capabilities.md` and
  `tests/test_sdd_capabilities_661.py`. Nothing in a production module is changed.

### Build, CI and image facts that constrain the experiment

- The repo is Python-only. There is no `Cargo.toml` and no `*.rs` file (`git ls-files`).
- The image copies only `orchestrator/`, `config/`, `agents/` and `entrypoint.sh`
  (Dockerfile lines 120-146), so an `experiments/` tree never ships. `.dockerignore`
  currently does not exclude `experiments/`, though, and a local Rust `target/` would
  enter the build context.
- `.github/workflows/pr-validation.yml` runs:
  - `uv run --locked pytest -q` (`testpaths = ["tests"]`);
  - `ruff check orchestrator config tests tools`;
  - mypy;
  - a docker smoke build;
  - commit-lint. Commit-lint treats any path outside `^(tests/|docs/|\.github/)` as
    shipping and requires a releasable commit type.
- `tests/test_worker_isolation.py` and `tests/test_agent_inventory.py` already police
  module boundaries. A new isolation test fits that pattern.

### Deployed state checked

- `mctl_whoami`: authenticated to `https://api.mctl.ai` as `mctl-agent`, admin, team
  `admins`. This confirms the remote MCP endpoint the proxy would sit in front of.
- `$MCTL_GITOPS_ROOT/services/admins/`: the deployed mctl-agents services are
  `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement`.
  `mctl-agents-worker/values.yaml` pins image tag `1.89.0`. No runtime, proxy or
  `mctl-runtime` service exists in any tenant (`admins`, `karabu`, `labs` listed).
- `grep api.mctl.ai/mcp` over `$MCTL_GITOPS_ROOT/services`: no match. The MCP endpoint
  URL is not configured through gitops values here, and I did not assert where it is
  configured.
- Not observed: whether `api.mctl.ai/mcp` returns a per-request id header usable for
  correlation, and whether it accepts a static bearer token from a non-agent human user.
  Both are recorded under Open questions. Neither was treated as absent.

## Proposed solution

### Layout (all under one deletable directory)

```text
experiments/portable-runtime-rs/
  README.md               # what, how to run, how to delete; "EXPERIMENTAL, default-off"
  Cargo.toml / Cargo.lock # standalone crate (NOT a workspace member of anything); exact pins
  rust-toolchain.toml     # pinned stable toolchain
  src/main.rs             # clap CLI: doctor | init | proxy
  src/config.rs           # upstream URL, allowlist path, timeouts (TOML)
  src/credential.rs       # CredentialSource trait: TokenFile, EnvVar; Keychain/Loopback = stub + docs
  src/bridge.rs           # stdio MCP server <-> streamable-HTTP MCP client, allowlist, passthrough
  src/correlation.rs      # invocation id, args sha256, one stderr JSON line per call
  src/spawn.rs            # the ONLY child-spawn helper; env-scrubs credentials
  src/hostcfg.rs          # init: render host config (fixture, claude-code shape) to stdout
  fixtures/allowlist.toml # read-only tools: mctl_whoami, mctl_list_services, mctl_get_service_status
  fixtures/host-fixture/  # throwaway host config dir used by tests
  tests/                  # cargo integration tests incl. in-process fake upstream
  baseline/thin_adapter.py# minimal Python stdio->HTTP passthrough using the already-pinned mcp==1.29.0
  bench/measure.sh        # builds, measures size/start/RSS/latency for rust, baseline, direct
docs/spikes/746-portable-runtime.md   # the report + decision (ADR-style)
tests/test_portable_runtime_isolation.py  # boundary guard (pure Python, no cargo needed)
.github/workflows/portable-runtime-spike.yml  # optional; paths-filtered + workflow_dispatch
```

### Runtime behaviour

1. **`proxy` (J2).** The host spawns `mctl-runtime proxy`, and the runtime speaks MCP over
   stdio.
   - On `initialize`, the runtime connects to one upstream over streamable HTTP. The
     upstream is `https://api.mctl.ai/mcp` by default, overridable for the fake upstream.
     The runtime then lists the upstream tools.
   - `tools/list` returns upstream tools whose name is in the allowlist. `name`,
     `description` and `inputSchema` are copied verbatim, never re-authored.
   - `tools/call` for a non-allowlisted name returns `isError: true` with
     `{"reason_code":"not-eligible"}` and makes no upstream I/O.
   - `tools/call` for an allowlisted name is forwarded with `X-Mctl-Invocation-Id`, and the
     result object (content and `isError`) is returned unchanged.
   - An unreachable upstream or a timeout returns `provider-unavailable` or
     `provider-timeout`. An HTTP 401 or 403 returns `credential-rejected`.

   These names mirror ADR 017 section 7 where an equivalent exists. There is no retry with
   another credential, no cache, and no local result shaping. Result shaping or caching is
   evaluated on paper only (Q4), because adding it would create the data-custody problem
   the issue warns about.
2. **`init --host <fixture|claude-code>` (J1).** Renders the host MCP config JSON to
   stdout.
   - The rendered config contains `command` (absolute path of the binary), `args: ["proxy"]`,
     and either `env: {"MCTL_RUNTIME_TOKEN_FILE": "<path>"}` or a note telling the user to
     export `MCTL_TOKEN`. It never contains a token value.
   - `--dry-run` is the default. `--write` additionally requires `--config-dir`, and is used
     only by tests on `fixtures/host-fixture/` copied to a tempdir.
3. **`doctor`.** Checks, in order: binary version; which credential source would be used
   (name only, never the value); token file mode (`0600` required); upstream reachability
   through an `initialize` and `tools/list` round trip; allowlist parse and count; and
   which allowlisted tools are missing upstream. It exits non-zero on any failure.
4. **Credentials (J3).** `CredentialSource` is a trait with two implementations:
   - `TokenFile`: refuses a file readable by group or other;
   - `EnvVar`: `MCTL_TOKEN`.

   Keychain and loopback handoff are documented trait stubs that return `Unsupported`, and
   the report evaluates them. `spawn.rs` is the single child-spawn helper. It calls
   `env_remove` for `MCTL_TOKEN` and `MCTL_RUNTIME_TOKEN_FILE`, and it never formats a
   credential into args. Production paths spawn no child. A hidden `--spawn-probe <path>`
   flag exists so the test can exercise the helper, mirroring the stub-CLI technique in
   `tests/test_tool_subprocess_env.py`.

   The report states plainly what the runtime does not fix. With the `EnvVar` source the
   token is still in the runtime's own `/proc/<pid>/environ`, and the host also holds it if
   the host passed it. The `TokenFile` source avoids that. This is the evidence for Q5:
   does the runtime isolate credentials, or only move them?
5. **Preflight (J4).** The only local rule is the allowlist, which narrows and never
   grants. Tests prove that a locally allowed tool that the fake upstream answers with
   `DENY` or `REQUIRE_APPROVAL` (`isError: true`, structured text) reaches the host
   byte-identical with `isError: true`.
6. **Correlation (J5).** Each call emits one stderr JSON line with these fields:
   `ts`, `invocation_id` (UUIDv4), `host_request_id`, `tool`, `args_sha256` (over
   canonical JSON, the same idea as `policy_checkpoint.args_digest_of`), `upstream_session_id`,
   `upstream_request_id` (if the upstream sends `X-Request-Id`), `outcome`, `is_error`,
   `latency_ms`. Nothing is written to disk. Canonical evidence stays in MCTL (ADR 018).
7. **Commerce (J6).** Design note only, in the report. It gives a sequence diagram:
   host → runtime → upstream answers with a 402-style challenge → runtime surfaces it as a
   structured `isError` and does not pay → the client or provider settles under
   `mctl-api#616` rules → retry carries a receipt reference.

   The note also gives an interface sketch, `PaymentChallengeHandler` with only a
   `Refuse` implementation. Its conclusion question is whether payment belongs at this
   boundary or stays between client and provider (Q7). No wallet, key, or network payment
   code is written.

### Fake upstream and tests

The Rust integration tests start an in-process fake upstream: a minimal streamable-HTTP
MCP endpoint on `127.0.0.1:0`, built with the same HTTP stack as the runtime. Its tools
are scripted:

- `mctl_whoami` returns ok;
- `deny_tool` returns `isError` with "DENY: policy ...";
- `approval_tool` returns `isError` with "REQUIRE_APPROVAL ...";
- `slow_tool` sleeps past the timeout;
- `secret_tool` is present upstream but not on the allowlist.

Request-level knobs make the endpoint return 401, close the socket, or echo the received
headers so tests can assert on them. The fixture host is a test driver that spawns the
binary as a host would, with stdio JSON-RPC. CI never needs network access or a live
token. A live read-only call (`mctl_whoami` against `api.mctl.ai`) is an opt-in
measurement, gated by `MCTL_RUNTIME_LIVE=1`.

### Measurement harness

`bench/measure.sh` performs these steps:

1. Run `cargo build --release` and time it.
2. Record `stat -c %s` of the binary and the output of `ldd` or `file`, which gives the
   target-host file and dependency count.
3. Measure cold start to ready as the time from spawn to the `initialize` response,
   over N=20 runs (median and p95).
4. Read idle RSS from `/proc/<pid>/status` `VmRSS` after `initialize`, and RSS again
   during a `slow_tool` call.
5. Measure first-call and steady-state latency (N=100 calls) through the proxy against
   the fake upstream, compared with a direct streamable-HTTP client call. The overhead
   is the difference.
6. Run the same procedure for `baseline/thin_adapter.py`, using `uv run` with the
   repo's locked env. Also record the package and venv footprint.

Cross-builds:

- Linux amd64 (`x86_64-unknown-linux-musl`) and arm64 (`aarch64-unknown-linux-musl`) via
  `cargo-zigbuild` or `cross`;
- macOS arm64 on a `macos-14` runner in the optional workflow;
- Windows (`x86_64-pc-windows-gnu`) as a compile-only attempt.

Every outcome, including failures, goes in the report table.

### Report and decision

`docs/spikes/746-portable-runtime.md` contains:

- the current-state map and the friction list;
- the duplicate check against #242, #717, mctl-telegram#784, .github#34 / #652 and
  .github#173 / mctl-api#616;
- the measurements;
- the 14-row Rust-vs-thin-adapter/direct matrix from the issue;
- answers to Q1 to Q10;
- the J6 note;
- a GO-criteria checklist marked met, not met or unproven, each line with its evidence;
- exactly one decision token.

The decision rule is applied literally:

- If only J1 has value, the decision is `THIN_ADAPTER`.
- If docs and skills fix the measured friction, the decision is `NO_RUNTIME`.
- `PORTABLE_RUNTIME_*` requires all seven GO criteria to be met.
- `_RUST` additionally requires a measured packaging or sandbox advantage that outweighs
  adding Rust to the maintenance surface.

Repository and ownership recommendations, and drafted follow-up issue texts, are included
only if the decision is GO. The PR does not file them, so no human step is needed.

My prior, from the current state, is that remote MCP plus OAuth already covers the
mainstream hosts, so `THIN_ADAPTER` or `NO_RUNTIME` is the likely outcome. The report must
not rely on that prior. It must let the measurements decide.

### Repo hygiene (deletable)

- `.gitignore`: add `experiments/**/target/`. `.dockerignore`: add `experiments/`, so the
  image build context is unaffected.
- `pr-validation.yml` commit-lint: extend the non-shipping regex to
  `^(tests/|docs/|\.github/|experiments/)`. This is accurate, because the Dockerfile copies
  nothing from `experiments/`. The alternative is a `feat(experiments):` commit that cuts a
  release with an unchanged image, which is worse.
- `tests/test_portable_runtime_isolation.py` asserts:
  - no file in `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh` or
    `pyproject.toml` references `experiments/` or `mctl-runtime`;
  - the Dockerfile has no `COPY experiments`;
  - `.dockerignore` excludes `experiments/`;
  - no `Cargo.toml` exists outside `experiments/portable-runtime-rs/`.

  The test skips itself when the directory is absent, so deleting the experiment leaves
  it inert.
- `.github/workflows/portable-runtime-spike.yml` runs `cargo test`, `cargo clippy` and the
  cross-build matrix only on `paths: experiments/portable-runtime-rs/**` or
  `workflow_dispatch`, with `permissions: contents: read`. It is not a required check.

## Alternatives

1. **Build the proof in Python inside `orchestrator/` and reuse `CapabilityGateway`
   directly.** This gives maximum reuse, but it violates "isolated, default-off,
   deletable". The worker must also never load `mcp` or `claude_agent_sdk` at module
   scope (`tests/test_worker_isolation.py`). It would also answer Q2 (Rust or not) by
   omission. Rejected. A thin Python adapter is still built, as the measurement baseline,
   under `experiments/` only.
2. **Create `mctlhq/mctl-runtime` now.** This is explicitly forbidden before GO (invariant
   9). Repository ownership is a deliverable of the spike, not a premise. Rejected.
3. **Bootstrap only: a config generator script or skill, with no proxy.** It is cheap, and
   it may well be the final answer (`THIN_ADAPTER` / `NO_RUNTIME`). It cannot produce the
   J2, J4 and J5 evidence the issue requires to rule a runtime in or out, though. It is
   kept as the comparison baseline in the matrix, not as the build.
4. **Wrap the Python baseline as a PyInstaller or shiv single file, as the
   `PORTABLE_RUNTIME_OTHER` candidate.** This is not built. Its size and startup are cited
   as ecosystem evidence in the matrix, with the caveat that it was not measured. Building
   it would double the spike's scope.

## Platform impact

- **Migrations / backward compatibility.** None. No production module, image, manifest,
  API or schema changes. Running workers are unaffected.
- **Resource impact.** CI: an optional paths-filtered workflow. The Rust build is a few
  minutes and runs only when the experiment changes, and the macOS runner is used only
  there. The image build context shrinks or stays the same thanks to the `.dockerignore`
  entry.
- **Risks and mitigations.**
  - *Rust enters the maintenance surface.* Confined to one directory, not required by any
    check, and removed by deletion. The isolation test prevents leakage into production
    paths.
  - *Token leakage.* There are four mitigations:
    - no argv token path exists;
    - `spawn.rs` scrubs the child environment;
    - `init` output is tested to contain no token value;
    - the token file mode is enforced.

    Tests use a sentinel token string and grep every spawned argv, env, stdout and stderr
    capture for it.
  - *The runtime becomes a policy authority.* The only local rule is an allowlist, which
    is a narrowing. Tests assert remote DENY and REQUIRE_APPROVAL pass through with
    `isError: true`.
  - *Live-API dependence makes CI flaky.* Live calls are opt-in only, and CI uses the fake
    upstream.
  - *Dependency supply chain (crates).* `Cargo.lock` is committed, and a `cargo deny` or
    `cargo audit` step runs in the optional workflow. rustls is used, not OpenSSL, so the
    binary stays static.
  - *Commit-lint regex change hides real shipping changes.* Only `experiments/` is added,
    and the isolation test proves nothing from it is copied into the image.
- **Open questions** (also in requirements.md):
  - the upstream per-request id header is unobserved;
  - `rmcp` versus a hand-rolled JSON-RPC subset;
  - macOS runner availability;
  - Python as the sole measured baseline;
  - the commit-lint allowlist edit versus a `feat` commit;
  - whether `api.mctl.ai/mcp` accepts static bearer tokens for human users (relevant to the
    J3 credential UX, not observed).
