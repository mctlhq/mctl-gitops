# Tasks: issue-373-spike-mctl-security-intelligence-siem-ru

Precondition: the owner's GO for this proposal on the DevLoop decide page. Do not add
`agents:intake` to #373, open follow-up issues, or touch mctl-gitops.

- [ ] 1. Add `docs/spikes/security-intelligence/fixtures/SHA256SUMS` pinning the existing `normalized.jsonl`, `allowset.json`, `expected.json` byte-for-byte (do not edit the fixtures) — DoD: `sha256sum -c` passes from the fixtures directory.
- [ ] 2. Implement `docs/spikes/security-intelligence/offline_eval.py` (stdlib only) with the CLI `--fixtures --allowset --expected --out`, Revision 2 validation order, rule `EG373-R1/1`, in-memory replay/conflict by `(source,id)` + canonical digest, five-field canonical JSON output, summary, exit codes 0/1/2 (depends on 1) — DoD: `python3 -I offline_eval.py ...` on the frozen files exits 0 and every row equals `expected.json`.
- [ ] 3. Add isolation assertions to the harness: forbidden-field scan of outputs and a check that no network/subprocess client module is loaded (depends on 2) — DoD: injecting a destination string into an output row in a test makes the run exit 1.
- [ ] 4. Add null, substring and ignore-port baselines and the discrimination check (depends on 2) — DoD: summary lists null failing E2/E7/E9, substring failing E9, ignore-port failing E7; a baseline passing its designated case yields exit 1.
- [ ] 5. Add `docs/spikes/security-intelligence/tests/test_offline_eval.py` covering T1-T8 (depends on 2-4) — DoD: `python3 -I -m unittest discover -s docs/spikes/security-intelligence/tests -v` passes locally.
- [ ] 6. Run the harness once and record the measured per-case results, disposition counts and descriptive wall time / peak memory (host-labelled) in the report (depends on 5) — DoD: numbers in the report match a committed `results.json` produced by the run.
- [ ] 7. Add Revision 3 sections D1-D7 to `docs/spikes/security-intelligence.md` above the preserved Revision 2 text: pinned D1 matrix (gitops `d29edb4a`, `.github` SHA at implementation time, UNKNOWN rows explicit), D2 definitions reusing #209, D3 comparison with sourced-or-"unverified" version/license cells, D4 executed vs NOT RUN scenarios, D5 trace with non-implemented arrows, D6 primary DEFER + secondary EXTEND_NATIVE_DETECTION (not authorized), D7 review request (depends on 6) — DoD: every claim cites a path/SHA or is tagged UNKNOWN / unverified; no live measurement is claimed.
- [ ] 8. Add `roadmap/spikes/security-intelligence.yaml` (SpikeDefinition, `lifecycle: proposed`, issue `mctlhq/.github#373`, outcomes REUSE_EXISTING_STACK, EXTEND_NATIVE_DETECTION, ADOPT_FALCO_PILOT, ADOPT_SIEM_PILOT, CREATE_SECURITY_OPERATIONS_EPIC, DEFER, `timebox.decisionBy: "2026-12-31"`, `evidence.report`, no `decision`) — DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes and `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` passes.
- [ ] 9. Register the spike in `AGENTS.md` `# Spikes` and add the path filter plus `python3 -I -m unittest discover -s docs/spikes/security-intelligence/tests -v` step to `.github/workflows/workflow-tests.yml` (depends on 5) — DoD: workflow-tests runs and passes on the PR.
- [ ] 10. Open one PR referencing #373 (not closing it), requesting independent review; commits carry the `Agent:` trailer — DoD: PR open, CI green, issue labels unchanged.

## Tests

- [ ] T1. Conformance: each of E1-E12 matches `expected.json` exactly; counts are 3 MATCH_REFERENCE, 3 NO_MATCH, 1 REPLAY, 1 CONFLICT, 1 REJECT, 2 UNKNOWN, 1 COVERAGE_UNKNOWN.
- [ ] T2. Exit codes: frozen key -> 0; one mutated expected disposition -> 1; missing fixture file -> 2; SHA-256 mismatch -> 2.
- [ ] T3. Determinism: two runs produce byte-identical `results.json` (timing fields excluded or written to a separate section).
- [ ] T4. Baselines: null fails E2/E7/E9, substring fails E9, ignore-port fails E7; a patched baseline that passes its case flips the run to exit 1.
- [ ] T5. Isolation: no output row contains `.invalid`, `http`, tenant/user/client keys or incident/finding/proposal/approval keys; no network/subprocess module loaded during a run.
- [ ] T6. Replay state: a fresh process reprocessing E2 returns MATCH_REFERENCE again (no persisted state).
- [ ] T7. Robustness (test-local, not part of eval1 key): IP literal, IPv6, double dot, empty host, port 0/65536, extra field, string status -> UNKNOWN; unknown source -> REJECT.
- [ ] T8. Roadmap: the new SpikeDefinition validates and `roadmap/tests` stay green.

## Rollback

Revert the single PR. All changes are additive files under
`docs/spikes/security-intelligence*`, `roadmap/spikes/security-intelligence.yaml`, one
`AGENTS.md` line and one CI step; no runtime, gitops, data or label state is touched, so
reverting restores Revision 2 exactly. If only the roadmap manifest breaks publication,
revert that file alone.
