# Tasks: issue-308-spike-agent-identity-cloudflare-web-bot

- [ ] 1. Current-state and duplicate map. Inventory outbound HTTP, MCP and browser egress paths in mctl-api, mctl-agents, mctl-telegram, claude-remote and mctl-support (code at pinned 40-hex commits). Inventory mctl-gitops `infrastructure/cloudflare/` (including `modules/spoofed-crawlers`) and tenant `networking` settings. Use `mctl_list_services` where available. Search for prior request-signing or egress-gateway work. Record owner, HTTP client, tenant/principal propagation, secret custody, audit key and gates. — DoD: a map table in the report with evidence tags. "No prior PoC found" names the repos and queries searched.
- [ ] 2. Pin external facts (depends on nothing). Cover Cloudflare Web Bot Auth, Verified Bots, the Block AI bots and Personal Assistants announcement, IETF draft names and revisions, the Intermediary taxonomy, eligibility, plan and cost, and the submission and approval steps. — DoD: a pin table with URL and retrieval date. The three-level distinction (signature validity / BotBase Verified / per-site policy) is stated. Unfetched facts are marked `unknown (not observed)`.
- [ ] 3. Surface matrix (depends on 1, 2). Cover (a) server-side MCTL fetch / MCP fetch tool, (b) Claude/Codex built-in tool HTTP, (c) browser-use. — DoD: each row has every required column. Uninstrumentable clients are marked unsupported.
- [ ] 4. Reference harness `docs/spikes/cloudflare-agent-identity-web-bot-auth/` using Go 1.22, standard library only, with `model/{sign,directory,verify}.go`, `fixtures/keys.json` (fixture-only) and `README.md` (depends on 2). — DoD: `go vet ./... && go test ./...` passes offline. The signed request carries `Signature-Agent`, `Signature-Input` and `Signature`. The directory is served at `/.well-known/http-message-signatures-directory` with the correct media type and its own signature.
- [ ] 5. Negative controls in `harness_test.go` (depends on 4): unsigned, tampered component, expired, wrong key, rotated key, replay. — DoD: an expected vs observed table in the report. Replay is recorded as "accepted by signature alone", not as a pass.
- [ ] 6. Optional external probe `probe/` (build tag `probe`) against `https://crawltest.com/cdn-cgi/web-bot-auth`, only if outbound access is permitted (depends on 4). — DoD: exact status and trace recorded, or the precise blocker recorded. No claim of Verified status.
- [ ] 7. Identity separation, signing boundary, key lifecycle (rotation, revocation, compromise), replay/idempotency, and redirect, proxy, retry, cache and SSRF controls. Include the architecture sketch (depends on 1, 3, 5). — DoD: report sections exist. No user, tenant or principal identifier appears in any public artifact or header. The private key is held by a central signer only.
- [ ] 8. Threat matrix and options comparison: sign-at-client vs central egress adapter vs no browser-use. Add the BotBase submission requirements, the classification-validation plan, and a separate section on transitive-trust / `Forwarded` (depends on 7). — DoD: every threat row from requirements.md is present. Cost, lock-in and fallback are stated.
- [ ] 9. Proposed verdict. Exactly one of ADOPT/LIMITED/DEFER/REJECT, with GO surface, revisit trigger (if DEFER) and follow-up proposals attached to mctl-api / mctl-agents / mctl-gitops (depends on 3, 8). — DoD: one verdict line. Follow-ups are proposals only, and no issues are opened.
- [ ] 10. Add `roadmap/spikes/cloudflare-agent-identity-web-bot-auth.yaml` (`lifecycle: proposed`, outcomes ADOPT/LIMITED/DEFER/REJECT, `execution.devloop: true`, `evidence.report`, no `decision`) and the `AGENTS.md` `# Spikes` entry (depends on 9). — DoD: `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` exits 0.

## Tests

- [ ] T1. `cd docs/spikes/cloudflare-agent-identity-web-bot-auth && go vet ./... && go test ./...` passes without network access.
- [ ] T2. Positive test: the local verifier accepts the signed synthetic request, and the directory response verifies against its own key.
- [ ] T3. Negative tests: unsigned, tampered `@authority`, expired, wrong `keyid`, and removed (rotated) key are each rejected with a distinct reason. Replay is accepted by the signature check, and the test asserts and documents that.
- [ ] T4. A test asserts that no header or directory field contains the fixture tenant/principal ids used in the harness (no-PII check).
- [ ] T5. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and `python -m pytest roadmap/tests` pass.
- [ ] T6. Manual review checks that the report contains no secrets, no private key material other than documented fixture seeds, and no user payloads.

## Rollback

Docs and manifest only. Revert the PR. Nothing is deployed, registered or
published, so there is no external state to undo. If the optional probe ran,
its fixture key was never published, so no revocation is needed.
