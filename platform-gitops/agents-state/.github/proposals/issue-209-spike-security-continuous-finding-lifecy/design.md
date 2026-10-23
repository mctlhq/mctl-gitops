# Design: issue-209-spike-security-continuous-finding-lifecy

## Current state

`mctlhq/.github` (clone at `7210e36`) is the organization meta-repository. It holds roadmap
manifests, contract schemas, spike reports and shared CI. Relevant content:

- `AGENTS.md` indexes active plans and spikes. The only spike so far is
  `docs/spikes/agent-governance-decision-assurance.md` (mctlhq/.github#182). It fixes the
  report conventions this spike follows: an evidence-pin table with 40-hex commits and read
  dates, `[I]`/`[P]` tags, `unknown (not observed)` instead of guesses, explicit non-claims,
  and "the recommended roadmap action is text only".
- `roadmap/epics/agent-runtime-assurance.yaml` (#151, owner `mctl-agents`) defines the
  phases contract, harness, suites, adaptation, validation and integration. It also defines
  success criteria including "A model-reported finding is never accepted as ground truth
  without reproducible validation" and "Findings bind to exact scenario, runtime and target
  versions". Its scope is agent, MCP and tool execution boundaries, not source-code CVEs.
- `events/README.md` and `events/schemas/event-envelope.v1.schema.json` define the existing
  principle "the event is disposable; the source is canonical", with `id` as a stable dedup
  key derived from the source's own identity (for example `X-GitHub-Delivery`). A provider
  webhook in this design reuses that principle rather than a new delivery model.
- `.github/workflows/claude-review.yml` (lines ~344-392) and `agy-review.yml` (~191-222)
  produce PR review findings tagged P1/P2/P3 as inline comments bound to `commit_id`. Those
  are security-relevant signals with no identity beyond the comment, no dedup and no lifecycle
  after merge.
- `.github/dependabot.yml` covers only `github-actions` version updates for this repo.
- Test conventions: stdlib `unittest`, run with `python3 -m unittest discover -s <dir>`
  (`.github/workflows/workflow-tests.yml:38`, `events-validate.yml:28`).

Deployed state checked:

- `mctl_list_services(team=admins)`: argocd ok, complete. The `mctl-agents-worker`, `-exec`
  and `-implement` services run `ghcr.io/mctlhq/mctl-agents:1.91.0`. No security-finding
  service or webhook receiver is deployed in `admins`.
- `mctl_get_epic_status(agent-runtime-assurance)`: lifecycle `active`. All 7 work items are
  `unknown`, reason `unbound`, at state_revision `7f132837`. The roadmap does not bind
  mctl-agents#694-#700 yet, so `AssuranceFinding`'s implemented shape was not observed.
- `$MCTL_GITOPS_ROOT/agents-state/`: 156 `requirements.md` files cite a CVE id.
  CVE-2025-54236 appears in 6 `mctl-api` proposals (`pgx-sqli-cve-2025-54236`,
  `pgx-sqli-patch`, `pgx-cve-sql-injection`, `pgx-sql-injection-fix`, `pgx-upgrade-v592`,
  `pgx-critical-memory-safety-cve-v2`). Only the first has a `.status.yaml`
  (`status: merged`, `pr: mctl-api#40`, `merge_commit: 92f579a8...`). It holds no
  verification field, although its requirements say a Trivy/Dependabot scan must show zero
  findings. CVE-2026-32283 appears in 13 proposals (mctl-agent, mctl-api). CVE-2026-24046
  appears in 9 (mctl-portal). 31 files mention Trivy and 2 mention CodeQL or code scanning.
- `$MCTL_GITOPS_ROOT/agents-state/OPERATOR.md`: the implementer reads only
  `requirements.md`, `design.md`, `tasks.md` and `.status.yaml`. The status lifecycle ends at
  `merged`/`rejected`, with no verified or reopened state.
- `grep trivy|codeql` over `argo-workflows`, `helm-charts`, `governance` and `mcp` found
  nothing. Where Trivy and CodeQL actually run (per-repo GitHub Actions) was **not
  observed**. That must be read from each repo's `.github/workflows` during the spike.
- Claude Security public article (fetched 2026-10-23): public beta, Claude Enterprise only.
  It covers baseline plus continuous rescans, multi-repo projects, an editable threat model,
  findings marked fixed when the fix ships (wherever it was made) and auto-reopened on
  re-detection, and an API to list/read/resolve/reopen findings with personal access tokens
  that carry user permissions. Webhooks fire on new findings only. An MCP connector exists,
  plus RBAC. No API field or webhook event names are published. Live access: none.

Current-state summary (the D1 hypothesis the spike must confirm): there are at least six
finding representations. They are GitHub code scanning alerts, Dependabot alerts, Trivy CI
output, Claude/agy review comments, agents-state service-agent CVE proposals and manual
issues, with `AssuranceFinding` planned as a seventh. None of them shares a dedup key. All
except provider-native alerts end at "PR merged", and none records verification against the
landed revision.

## Proposed solution

Deliver one spike report and one bounded fixture experiment in `mctlhq/.github`. No runtime
component changes.

### 1. Report `docs/spikes/security-finding-lifecycle.md` (D1-D7)

The structure mirrors the #182 report: header and non-claims, then evidence pins (shallow
clones of mctl-api, mctl-agents and mctl-gitops at 40-hex SHAs, and the per-repo workflow
files that run CodeQL/Trivy), then D1 to D7.

- **D1** lists, per source, the ten Q1 attributes, with citations.
- **D2** is the 12-row matrix. The GitHub column is mapped from the public REST/webhook docs:
  alert `number` per repo plus `rule.id`; `state` open/dismissed/fixed;
  `dismissed_reason`/`dismissed_by`; `most_recent_instance.commit_sha`/`ref`/`location`;
  `fixed_at`; and the `code_scanning_alert` webhook actions created, fixed, reopened,
  closed_by_user and appeared_in_branch. The Claude Security column comes from the article,
  with unnamed fields marked `unknown`. The Runtime Assurance column comes from the #151
  manifest plus mctl-agents at a pin.
- **D3** proposes the boundary "**introduce `SecurityFinding` that references
  `AssuranceFinding`**". Assurance stays the producer and owner of probe, replay and
  promotion. A confirmed `AssuranceFinding` is one provider (`provider=mctl-assurance`) whose
  verification strength is `deterministic_replay`. Extending `AssuranceFinding` is rejected
  because it would import CVE and scanner semantics into a harness whose success criteria
  restrict it to agent boundaries.
- **D4** is the minimal candidate contract, only if D1 and D5 confirm the gap:
  - Identity: `sf_` id. Canonical dedup key = hash(`vuln_class_id` (CVE/GHSA/CWE plus rule id,
    or assurance scenario id), affected repository identity, `component` (package or path
    fingerprint)). Provider observations are keyed by (`provider`, `source_finding_id`) and
    deduplicated by delivery id, following `events/README.md`.
  - The record stores references only: repository identity, vulnerable revision and fixed
    revision (immutable SHA), evidence refs (hash plus URI), threat-context ref
    (optional, immutable revision of declarative service metadata in gitops), and a
    `work_item_id` ref. Provider severity is kept as an evidence attribute. MCTL severity is
    derived, and it never feeds authorization.
  - States: `open`, `triaged`, `fixing`, `awaiting_verification`, `resolved`, `reopened`,
    `unverifiable`, and `dismissed{false_positive|accepted_risk|duplicate|not_applicable|provider_withdrawn}`.
  - Transitions are computed deterministically by MCTL from recorded evidence. Providers
    only append observations. Humans only perform dismiss and triage, with actor, authority
    and reason.
  - Verification strength is ordered as
    `deterministic_regression_test` > `assurance_replay` > `scanner_rerun_exact_revision` >
    `provider_claim` > `manual`. `resolved` requires the landed revision, a declared
    mechanism, and a result bound to that revision whose strength is at least the policy
    minimum (default `scanner_rerun_exact_revision`). A failed or unavailable scan goes to
    `unverifiable`, never to absent.
  - Reopen: regression evidence for the same canonical key on a revision that descends from
    the fixed revision moves `resolved` to `reopened`. It requires N=2 consecutive scanner
    observations, or one deterministic test. A different key, or a dismissed finding, gets a
    linked successor and evidence, not a reopen.
  - Remediation: a finding is a WorkItem *source reference*, not a WorkItem. One open
    remediation is allowed per canonical key, using the existing `execution_request_open`
    guard semantics of `mctl_request_work_item_execution`. The DevLoop id stays derived from
    the issue.
  - Minimal surface (text only): `list`, `get`, `start_remediation`, `request_verification`,
    `dismiss`. There is no generic set-state operation.
- **D5** is the experiment results (below).
- **D6** is the ownership map. Proposed owners: durable store and API in `mctl-api`;
  remediation hookup and verification runner in `mctl-agents`; webhook and credential
  config only in `mctl-gitops`; Runtime Assurance unchanged (#151). Each row says
  extend/create, priority and dependency. No new epic.
- **D7** gives the recommendation. The hypothesis to confirm is `ADD_SECURITY_FINDING_CONTRACT`.
  The report must apply this decision rule. If D1 shows that existing provider-native
  lifecycles (GitHub `fixed`/`reopened`) plus issue automation already give dedup and
  verified closure for every MCTL source, the answer is `NO_NEW_CONTRACT`. If the capability
  needs more than about three independent slices across repos, the answer is
  `CREATE_SECURITY_EPIC`. Otherwise the answer is `ADD_SECURITY_FINDING_CONTRACT`.

### 2. Experiment `docs/spikes/security-finding-lifecycle/`

- `fixtures/`: a GitHub `code_scanning_alert` webhook payload shaped from public docs
  (created, fixed and reopened actions, synthetic repository, synthetic SHAs, no code), a
  Dependabot/Trivy-shaped CVE-2025-54236 observation, a Claude-Security-shaped fixture
  (fields labelled hypothetical), and an `AssuranceFinding`-shaped confirmed replay.
- `model.py` is a stdlib-only reference state machine, about 200 lines. It provides
  `ingest(observation)`, `link_remediation(key, work_item_ref)`, `record_merge(sha)`,
  `record_verification(sha, mechanism, result)` and `dismiss(actor, authority, reason)`.
  Transitions are derived from evidence, and an in-memory dedup index covers delivery ids
  and canonical keys. It is reference code, not a service.
- `tests/test_lifecycle.py` covers the full path, duplicate delivery, cross-provider
  dedup, merged-is-not-resolved, unknown-is-not-absent, the flapping guard, dismissed plus
  regression giving a linked successor, and provider text being unable to change state.
- CI: add a step `python3 -m unittest discover -s docs/spikes/security-finding-lifecycle/tests`
  to `.github/workflows/workflow-tests.yml`, and add the path to its `paths:` filter.

### 3. `AGENTS.md`

Add a Spikes entry pointing to the report (for #209).

## Alternatives

1. **`EXTEND_ASSURANCE_FINDING`**: add CVE and scanner provenance to `AssuranceFinding`.
   Dropped as the default. It widens the #151 contract beyond its success criteria (agent and
   MCP boundaries, harness-generated probes). The assurance work items are still unbound, so
   it would couple a scanner-facing lifecycle to an unbuilt harness. The report still
   evaluates this option.
2. **`NO_NEW_CONTRACT`**: rely on GitHub alerts plus issue automation and agents-state
   `.status.yaml`. Dropped as the default, given the observed evidence: six proposals for one
   CVE, `merged` as the terminal state with no verification, no reopen path, and no
   cross-provider key. Claude Security's and GitHub's own fixed/reopen logic is per-provider
   and is not bound to MCTL execution evidence. It stays the fallback if D1 disproves the gap.
3. **Build directly into mctl-api now**: rejected. The issue requires a spike first, and the
   non-goals forbid production rollout. A reference model in `.github` proves the semantics
   cheaply, and the owner repos implement later.

## Platform impact

- No migrations, no runtime change, no deployed component, no roadmap manifest change.
  This repo gains one markdown report, fixtures, a stdlib Python model with tests, a
  one-line `AGENTS.md` entry and one CI step.
- Backward compatibility: nothing consumes the new files.
- Resource impact: one additional unittest run of under a second in `workflow-tests.yml`.
- Risks and mitigations:
  - The fixtures could leak sensitive content. Mitigation: synthetic repositories and SHAs,
    no code excerpts, only identifiers, digests and public CVE ids.
  - The reference model could be mistaken for the canonical schema. Mitigation: the header
    labels it non-normative, and D4 is a candidate for owner review.
  - The Claude Security shape is unverified. Mitigation: fields are labelled hypothetical,
    and the contract has no dependency on Claude-specific concepts.
  - Prompt injection via provider text. Mitigation: the model never branches on description
    or severity text, and a test asserts it.
