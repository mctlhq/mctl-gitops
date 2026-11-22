# Tasks: issue-376-spike-mcp-apps-write-once-run-across-ai

Scope is the Phase 0 evidence slice in `mctlhq/.github`. Tasks 9-13 are follow-ups in other repositories and are listed for the backlog only. Each one needs its own issue and a separate owner approval, and none is implemented under this proposal.

- [ ] 0. Conform issue #376 to the current `.github/ISSUE_TEMPLATE/spike.yml` on `main` before approval. Re-fetch the template, then:
  - set the title to `spike: MCP Apps write once, run across ChatGPT, Antigravity and Claude`;
  - prepend the template block (`Source: mctlhq/.github#376`, `Question:` as in the SpikeDefinition, `Outcomes: ADOPT_STANDARD_ONLY | ADOPT_WITH_THIN_HOST_ADAPTERS | DEFER`, `Lifecycle: proposed`, `Related: mctlhq/mctl-telegram#569, #650; mctlhq/.github#35, #44, #258, #261, #373, #375`, `Why mctl:`) and keep the existing body after it;
  - add the labels `spike:scout` and `agents:intake`;
  - check for an existing spike with the same Source.
  DoD: re-read issue title, body and labels against the template, record the result in the PR description, and make no workflow restart until it conforms.
- [ ] 1. Add `roadmap/spikes/mcp-apps-portability.yaml` exactly as in design.md section 1 (`lifecycle: proposed`, no `decision`, no `epic`). DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes, and `roadmap/tests/test_validate_spike.py` still passes.
- [ ] 2. Write `docs/spikes/mcp-apps-portability/host_matrix.json`, seeded from the sources. Cover every contract point listed in requirements.md for every host column. Set:
  - `documented` with URL and access date: re-read each vendor page in the issue (ext-apps API and spec `2026-01-26`, OpenAI chatgpt-ui and extensions, Antigravity mcp-apps, Claude getting-started, entry-points, app-tools and the rollout article);
  - `fixture_tested` only for what the Telegram `mcpprobe` row shows;
  - `unknown` everywhere else.
  Every cell names ext-apps `v2.1.0` and spec `2026-01-26`. DoD: no `real_host_verified` cell, and the validator from task 3 passes.
- [ ] 3. Implement `docs/spikes/mcp-apps-portability/matrix.py`, `bridge_check.py` and `bundle_scan.py`: stdlib only, run with `python3 -I`, rules as in design.md section 1. Pin the allowed View-to-Host method set to spec `2026-01-26`. DoD: each script has `--help`, exits non-zero on violations, and its output is deterministic.
- [ ] 4. Add fixtures (depends on 3):
  - `telegram-triage-0.1.0.transcript.json`, reconstructed from mctl-telegram `internal/mcpui/triage.html` at `25e6485`: `ui/initialize {}`, then a View `tools/list`, then `tools/call get_unread_messages`, plus a `tool-result` handled by name;
  - a conformant minimal transcript;
  - a copy of the mctl-telegram `triage.html` bytes at `25e6485`, with its SHA-256 recorded;
  - matrix fixtures (valid, forged verified, mixed bundle hash).
  DoD: the fixtures carry their source commit and are referenced by tests.
- [ ] 5. Add `docs/spikes/mcp-apps-portability/tests/` (unittest) covering T1-T6, and wire the folder into `.github/workflows/workflow-tests.yml` paths and a step `python3 -I -m unittest discover -s docs/spikes/mcp-apps-portability/tests -v` (depends on 3, 4). DoD: CI green.
- [ ] 6. Write `docs/spikes/mcp-apps-portability.md` (depends on 2-4). It contains:
  - Question and Non-claims ("no real host exercised"), plus Evidence tags;
  - the matrix rendered by `matrix.py`;
  - the existing-work inventory with repo@revision and path, from design.md;
  - the three reading-based Telegram findings, each tied to its failing fixture;
  - the ADR (options A, B, C, with C recommended);
  - the PoC plan, security model, gates G1-G6, backlog, P1/P2/P3 risks and the product order;
  - an empty decision block for the owner.
  DoD: all three outcomes are described with the evidence that would select each, and no verdict is claimed.
- [ ] 7. Write the operator runbook as a section of the report: host and account prerequisites, the deployment choice (a throwaway or preview instance with `MCP_APPS_ENABLED=true` and a read-only link set, via an owner-approved mctl-gitops PR), the step-by-step check per gate, the capture format (screenshot sanitisation checklist, devtools transcript, `resources/read` hash, audit lines by `trace_id`), throwaway-account cleanup, and how to record `cause`. Tag it as an extension of mctlhq/mctl-telegram#650, not a parallel run. DoD: each step maps to a matrix cell and a gate.
- [ ] 8. Add one bullet under `# Spikes` in `AGENTS.md` linking the report (depends on 6). DoD: the link resolves.

Backlog (separate issues and approvals, not part of this PR):

- [ ] 9. mctl-telegram: bridge conformance fix plus a read-only UI link set (no `send_message`/`prepare_send_message` in `addToolUI` while read-only), entry tool `get_unread_messages {}`, a `Version` bump, the bundle SHA in `_meta`, and a headless golden test (depends on 5 being merged so the checker exists). Owner: mctlhq/mctl-telegram.
- [ ] 10. mctl-gitops: an owner-approved flag flip on a non-production or throwaway instance only (depends on 9). Owner: mctlhq/mctl-gitops.
- [ ] 11. Operator run under #650 that fills the matrix and evaluates G1-G6 (depends on 10). Owner: a human operator.
- [ ] 12. mctl-api: a read-only DevLoop Run Inspector MCP App on the existing work-item read tools, with no approval tools linked (depends on 11 G1-G4 GO, and #261). Owner: mctlhq/mctl-api.
- [ ] 13. Owner verdict in `roadmap/spikes/mcp-apps-portability.yaml` (`decided`, follow-ups for Glovo, SeerrSense and Alice), plus a decision on Go helper extraction after measuring the 9/12 duplication (depends on 11, 12).

## Tests

- [ ] T1. `matrix.py` rejects a `real_host_verified` cell missing any of date, host_build, plan, endpoint, bundle_sha256, artifact or operator, and rejects a `documented` cell without a URL and access date.
- [ ] T2. `matrix.py` rejects a matrix whose browser-host cells for one app carry different `bundle_sha256` values (G1), and accepts identical ones.
- [ ] T3. `bridge_check.py` fails the Telegram 0.1.0 transcript with three distinct findings: missing `appCapabilities`/`protocolVersion`/`appInfo`, View `tools/list`, and `tool-result` correlated by `params.name`. It passes the conformant transcript.
- [ ] T4. `bridge_check.py` fails a transcript that sends `ui/notifications/initialized` before the `ui/initialize` result, or calls a method outside the pinned allowed set.
- [ ] T5. `bundle_scan.py` passes the Telegram `triage.html` fixture on escaping (no `innerHTML` and the like) and on network access (no external URL), and fails synthetic bundles containing `innerHTML =`, `eval(`, `navigator.userAgent`, an unguarded `window.openai.` call, or `<script src="https://...">`. It prints a stable SHA-256.
- [ ] T6. The SpikeDefinition validates. With lifecycle `proposed` it has no `decision`, and the outcomes match the issue's three verdicts.
- Specified now, implemented in the product repos (tasks 9 and 12):
  - [ ] T7. With the read-only link set, `tools/list` shows `_meta.ui` only on read tools. A View `tools/call send_message` is refused by the server (scope or registration), whatever the host does with visibility.
  - [ ] T8. The View never sends `ui/update-model-context` or `ui/message` with Telegram message text (transcript assertion).
  - [ ] T9. The same read call issued as model-originated and as UI-originated (fixture host on the same session) yields identical authz decisions and audit records apart from an optional untrusted origin annotation.
  - [ ] T10. A cross-tenant id, missing scope, stale `state_version` and replayed or expired `confirmation_id` are each denied identically for both origins. A cross-tenant id answers the same as not-found.
  - [ ] T11. Headless golden: `content[].text` is byte-equal with `MCP_APPS_ENABLED` on and off for every App-linked tool.
  - [ ] T12. Degradation: with a fixture host advertising no display modes and no `ui/message`, the dependent controls are absent and no error is logged.

## Rollback

Phase 0 is docs, JSON, stdlib scripts and one CI step in `mctlhq/.github`, so reverting its PR restores the prior state, and no runtime, GitOps or tenant is touched. If the CI step proves flaky, drop only its `workflow-tests.yml` entry. Backlog product slices roll back independently:
- mctl-telegram by unsetting `MCP_APPS_ENABLED`, which is the env-only drop-back documented in `internal/config/config.go`;
- the flag flip by reverting the mctl-gitops values PR;
- mctl-api by its own feature flag, defined in that issue.
A DEFER verdict leaves the artifacts as the recorded measurement.
