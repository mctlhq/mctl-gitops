# Tasks: issue-2292-ci-agents-pin-the-corrected-agent-isolat

- [ ] 1. Confirm mctlhq/mctl-agents#921 has merged. Pick the pinned commit (at or after the #921 merge) and
  record the auditor's JSON output contract: row fields, key, version/schema fields, agent-step scope naming,
  and whether it emits an `allow-agent-ingress` row. — DoD: the commit SHA and contract notes are written into
  `scripts/agent-isolation/README.md`. If #921 is still open, stop: no gate is built on the faulty auditor.
- [ ] 2. (depends on 1) Vendor the auditor verbatim into `scripts/agent-isolation/auditor/` and write
  `scripts/agent-isolation/auditor.pin.json` (repo, 40-hex commit, `includes: [mctlhq/mctl-agents#921]`, files
  with source path, vendored path and sha256, auditor/output schema version or null). — DoD: `sha256sum` of each
  vendored file matches the pin, and the bytes match `raw.githubusercontent.com/mctlhq/mctl-agents/<commit>/<path>`.
- [ ] 3. (depends on 2) Write `scripts/validate-agent-isolation-baseline.py`. It covers pin integrity,
  `--verify-upstream`, the auditor subprocess (`python3 -I`, non-zero/exit 2/non-JSON/schema fails), baseline
  load (missing/schema/duplicate/pin-mismatch fail closed), the status comparison table, the peer check,
  enforcement of the `owner`/`issue` fields, the fixed `POD_SECURITY_OWNED` table, the step summary, and local
  `--regenerate [--out]`. — DoD: the script runs locally against the clone, and CI's invocation has no code path
  that writes `baseline.json`.
- [ ] 4. (depends on 3) Generate `scripts/agent-isolation/baseline.json` with `--regenerate` from current main.
  Assign `owner` per row. Mark every non-enforced row with its owning issue: the #807 gaps G1-G6 or later
  follow-ups. Where no issue exists, file one or reference mctlhq/mctl-agents#807. — DoD: the gate passes on
  current main, and no non-enforced row lacks `issue`.
- [ ] 5. (depends on 3) Add fixtures under `scripts/tests/fixtures/agent-isolation/{valid,invalid}/` and a
  `--selftest` that replays them. It includes the #921 namespace+pod-peer semantics fixture run through the real
  pinned auditor, and mutation replay (a)-(d) on a temp copy of `platform-gitops/`, with (d) also asserting that
  `scripts/validate-agent-pod-security.py --dir <copy>` fails. — DoD: `--selftest` prints `selftest ok`, and
  each invalid fixture fails for its intended reason only.
- [ ] 6. (depends on 4, 5) Wire `.github/workflows/validate-manifests.yml`. Add the step "Validate agent
  isolation matrix against baseline (#2292)" after "Validate agent pod security context" (`--selftest`, then the
  check). Add a conditional `--verify-upstream` step that runs when `scripts/agent-isolation/auditor*` changes
  vs. the base, and always on push to main. — DoD: the job is green on the PR. The step summary lists open gaps
  with their issues.
- [ ] 7. (depends on 2) Write `scripts/agent-isolation/README.md`. It covers the chosen source (vendored at a
  pinned commit) and why, the upgrade procedure (copy, re-pin, `--regenerate`, include the baseline diff and an
  explanation of each interpretation change in the PR body), the row ownership split, and the rule that CI
  never regenerates. Add a pointer line in `CLAUDE.md` "Secrets Management" runbook list, or a nearby section.
  — DoD: a reviewer can upgrade the pin from the README alone.

## Tests

- [ ] T1. Current main with the committed baseline: the gate passes and lists open gaps.
- [ ] T2. Mutation: remove `automountServiceAccountToken: false` from `cwft-mctl-agents-investigate.yaml`.
  The gate fails with a regression on that row.
- [ ] T3. Mutation: drop the `podSelector` from the `allow-agent-ingress` peer in
  `infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`. The gate fails.
- [ ] T4. Mutation: add an `agent_image` template without the peer controls. The gate fails (unbaselined row
  plus peer check), and `validate-agent-pod-security.py` also fails. The composed CI gate is red.
- [ ] T5. The #921 fixture: a namespace+pod peer is not reported at namespace-wide status, and a namespace-only
  peer is reported weaker.
- [ ] T6. Fail-closed cases: missing baseline, wrong `schema_version`, duplicate key (baseline and output),
  baseline/pin auditor mismatch, vendored-file sha mismatch, auditor exit 2, non-JSON output, a row turning
  `not-observed`, a gap row without `issue`, and a pod-security-owned field reassigned to the gate.
- [ ] T7. Gap lifecycle: an unchanged gap passes, `partial` to `absent` fails, and gap to `enforced` without a
  baseline update fails.
- [ ] T8. The `--verify-upstream` step fails when the vendored bytes differ from the pinned upstream commit.

## Rollback

Revert the PR. That removes the `validate-manifests.yml` step(s), `scripts/validate-agent-isolation-baseline.py`,
`scripts/agent-isolation/` (pin, vendored auditor, baseline, README) and the fixtures. Nothing is synced by
ArgoCD and no cluster state changes. To get relief without a revert, the new step alone can be removed.
