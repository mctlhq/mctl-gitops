# Tasks: issue-209-spike-security-continuous-finding-lifecy

- [ ] 1. Pin evidence. Shallow-clone mctl-api, mctl-agents and mctl-gitops, and record the
  40-hex SHAs and the read date. In mctl-agents, locate the `AssuranceFinding` contract
  (#694) or record `unknown (not observed)`. Read the per-repo `.github/workflows` that run
  CodeQL, Trivy or Dependabot for mctl-api, mctl-agents, mctl-agent and mctl-portal — DoD:
  the pin table is in the report, and every later claim cites `repo@sha:path`.
- [ ] 2. Write D1, the current-state map, in `docs/spikes/security-finding-lifecycle.md`
  (depends on 1). Cover code scanning/CodeQL, Dependabot/Trivy, Claude/agy review comments
  (`.github/workflows/claude-review.yml`, `agy-review.yml`), agents-state CVE proposals,
  manual issues and `AssuranceFinding`. Include measurements: 156 CVE-citing proposals; 6
  for CVE-2025-54236, with only `pgx-sqli-cve-2025-54236` carrying `.status.yaml` and that
  file holding no verification — DoD: each source has all ten Q1 attributes or
  `unknown` with a reason.
- [ ] 3. Write D2, the 12-row provider matrix (depends on 1). Map GitHub from the public
  REST and `code_scanning_alert` webhook docs, Claude Security from the public article
  (live access marked unavailable), and Runtime Assurance from #151 and the pin — DoD: no
  empty cells, and each cell has a citation or `unknown`.
- [ ] 4. Build the experiment in `docs/spikes/security-finding-lifecycle/`: synthetic
  `fixtures/*.json` (GitHub alert created/fixed/reopened, a Trivy/Dependabot CVE observation,
  a Claude-Security-shaped fixture labelled hypothetical, and an assurance replay) plus
  `model.py`, a stdlib state machine with transitions derived from evidence and no
  set-state primitive — DoD: the fixtures contain no secrets and no code bodies, and the
  model runs with `python3 -I`.
- [ ] 5. Add `tests/test_lifecycle.py` (T1-T8), then add a discover step and a path filter
  for it to `.github/workflows/workflow-tests.yml` (depends on 4) — DoD: CI green and tests
  pass locally.
- [ ] 6. Write D3 (boundary decision: `SecurityFinding` references `AssuranceFinding` unless
  the evidence says otherwise), D4 (candidate contract, only if the gap is confirmed) and
  D5 (experiment results with the commit SHA of the test run) (depends on 2, 3, 5) — DoD:
  exactly one boundary option is chosen and justified against the #151 success criteria.
- [ ] 7. Write D6 (the ownership map: mctl-api store/API, mctl-agents remediation and
  verification runner, mctl-gitops config only, #151 unchanged) and D7 (exactly one
  recommendation, applying the decision rule in design.md) (depends on 6) — DoD: there is a
  single recommendation token, the roadmap action is text only, and no manifest is edited.
- [ ] 8. Add the Spikes entry for #209 to `AGENTS.md` (depends on 7) — DoD: the link
  resolves.

## Tests

- [ ] T1. Full path: GitHub alert `created` gives `open`, then triage gives `triaged`, then
  linking a WorkItem gives `fixing`, with the vulnerable SHA recorded. Merging the fix SHA
  gives `awaiting_verification`. A `scanner_rerun_exact_revision` absent result on the fix SHA
  gives `resolved`. The regression fixture observed twice on a descendant revision gives
  `reopened`, with the same `sf_` id.
- [ ] T2. Duplicate delivery: the same delivery id ingested 3 times gives 1 finding, 1
  observation and 1 remediation reference.
- [ ] T3. Cross-provider dedup: Trivy plus Dependabot (or GitHub plus Claude-shaped)
  observations of CVE-2025-54236 on the same repository and component give 1 finding with 2
  observations, and a second `link_remediation` is refused as already open.
- [ ] T4. Merged is not resolved: `record_merge` with no verification leaves
  `awaiting_verification`.
- [ ] T5. Unknown is not absent: a verification result of `error` or `unavailable` gives
  `unverifiable`, never `resolved`.
- [ ] T6. A provider "fixed" claim alone is stored with strength `provider_claim` and does
  not resolve under the default policy.
- [ ] T7. Flapping guard: one regression observation on a resolved finding does not reopen
  it, and two consecutive observations do. A dismissed (`accepted_risk`) finding plus
  regression creates a linked successor or evidence entry. It does not silently reopen.
  Dismissal without actor, authority and reason is rejected.
- [ ] T8. Untrusted text: a fixture whose description contains state-changing instructions,
  or whose severity is set to "critical", causes no transition beyond what the evidence
  rules allow.

## Rollback

Every change is additive documentation, fixtures, test code and one CI step in
`mctlhq/.github`. Rollback is a revert of the PR. No runtime, data, roadmap manifest or
gitops state is touched, so nothing else needs undoing.
