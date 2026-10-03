# Design: issue-1408-chore-agents-implement-and-shepherd-cwft

## Current state

### The reference implementation (investigate)

`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
carries the shape this issue asks to mirror, in three places:

1. `spec.arguments.parameters` lines 92-129 declare `work_item_id`,
   `execution_id`, `temporal_workflow_id`, `temporal_run_id` and
   `execution_request_id`, each `value: ""`, each with a comment stating that
   empty means "absent" and that no default is invented.
2. `run-investigator`'s `container.env` lines 583-592 bind them to
   `WORKFLOW_WORK_ITEM_ID`, `WORKFLOW_EXECUTION_ID`,
   `WORKFLOW_TEMPORAL_WORKFLOW_ID`, `WORKFLOW_TEMPORAL_RUN_ID`,
   `WORKFLOW_EXECUTION_REQUEST_ID`. The comment at lines 578-582 names
   `scripts/validate-shell-param-interpolation.py` as the enforcement, not
   convention.
3. `container.args[2]` lines 376-399 additionally append them to argv with the
   `if [ -n "$VAR" ]; then set -- "$@" --flag "$VAR"; fi` idiom, because
   `run_issue_investigator.py` accepts `--work-item-id` /
   `--temporal-workflow-id` / ... (mctl-agents#267, #461, #451).

`tests/test_cwft_investigate_work_context_argv.py` slices that argv region
**verbatim** out of `container.args[2]` (markers: the
`if [ -z "$WORKFLOW_ISSUE_URL" ]` guard through the trailing `printf '\n'`),
runs it under `/bin/sh` with the six env vars set per case, and asserts on the
echoed `→ ...` line: omit-all, set-all, one-at-a-time, injection, and the
`issue_url` fail-fast regression. It is wired into
`.github/workflows/validate-manifests.yml` lines 282-291.

### The two templates that lack it

`cwft-mctl-agents-implement.yaml`:

- `spec.arguments.parameters` lines 88-116: `service`, `slug`, `force`,
  `max_proposals`, `agent_image`, `agent_version`. Nothing else.
- `run-implementer`'s `container.args[2]` lines 410-420 build argv:
  `set -- python -m orchestrator.run_implementer`, then `--service` /
  `--slug` conditionally from `$WORKFLOW_SERVICE` / `$WORKFLOW_SLUG`, then an
  unconditional `--max-proposals "$WORKFLOW_MAX_PROPOSALS"`, then the
  `printf '→' / printf ' %s' "$@" / printf '\n'` echo block.
- `container.env` lines 563-671 bind `IS_FALLBACK`, `WORKFLOW_SERVICE`,
  `WORKFLOW_SLUG`, `WORKFLOW_FORCE`, `WORKFLOW_MAX_PROPOSALS`, the budgets, the
  tokens — including `MCTL_USAGE_WRITER_TOKEN` (lines 649-654) and
  `WORKFLOW_NAME` (lines 655-659), whose comment already states it is "the join
  key of this run's usage records to its `agent_executions` row
  (`argo_workflow_name`)". That is the only correlation the usage producer gets
  here today.
- The same `run-implementer` template serves both the primary `implement` step
  and `implement-fallback`, so anything added to its `env` covers both attempts.

`cwft-mctl-agents-shepherd.yaml` is the same story:

- `spec.arguments.parameters` lines 106-132: `service`, `slug`, `dry_run`,
  `agent_image`, `agent_version`.
- `run-shepherd`'s `container.args[2]` lines 439-451 build
  `python -m orchestrator.run_shepherd` with `--service` / `--slug`
  conditionally and `--dry-run` under the `[ "$WORKFLOW_DRY_RUN" = "true" ]`
  boolean idiom, then the same three `printf` lines.
- `container.env` lines 604-692 bind `WORKFLOW_SERVICE`, `WORKFLOW_SLUG`,
  `WORKFLOW_DRY_RUN`, `IS_FALLBACK`, `MCTL_USAGE_WRITER_TOKEN` (674-679) and
  `WORKFLOW_NAME` (683-684) with the identical join-key comment.
- The shepherd's `review-fixing` path invokes the implementer as an **in-pod
  subprocess** (see the `GITHUB_TOKEN` comment at lines 643-647 — "the
  implementer subprocess's `gh repo clone` + `gh pr create` calls"), so that
  subprocess inherits whatever env this container has.

### The guard rails already in place

`scripts/validate-shell-param-interpolation.py` walks every CWFT and fails on
any `{{workflow.parameters.X}}` / `{{inputs.parameters.X}}` found inside
`container.command`/`args`, `script.source` or an `initContainers` command
(`shell_blocks`, `PLACEHOLDER`), unless the `(file, template, parameter)`
triple is in `BASELINE` or the parameter name is in `CONSTRAINED`. Neither set
contains `work_item_id`, `execution_id`, `temporal_workflow_id`,
`temporal_run_id` or `execution_request_id` — so "env only" is a CI-enforced
property of this change, not a reviewer's promise. `check_env_bindings`
additionally rejects a `script`-type template that reads a `PARAM_*` its own
`env` does not define, and rejects a duplicated `env` name.

Also relevant: the `CLAUDE.md` note that Argo snapshots templates at submit
time, so a template edit reaches new submits ~3 minutes after merge (ArgoCD
sync) and never disturbs an in-flight run.

## Proposed solution

Two YAML files change, plus one new test and one CI step. No `agent_image`
bump, no Python change in `mctl-agents`, no change to any other step of either
template.

### 1. Declare the five parameters (both templates)

Append to `spec.arguments.parameters`, after `agent_version`
(implement: after line 116; shepherd: after line 132), five entries with
`value: ""` and comments in the voice of the neighbouring entries. Each comment
states: optional; minted by the dev-loop control plane; **correlation only —
carried to the runner as env and NOT forwarded as a CLI flag**; empty means
absent and no value is ever derived; read by the usage producer
(`orchestrator/usage_ledger.py`) alongside the existing `WORKFLOW_NAME` join
key; mirrors gitops#1279 on `cwft-mctl-agents-investigate.yaml`; owner decision
4 of mctlhq/.github#50.

The "not a CLI flag" sentence is the load-bearing part of the comment: the next
person mirroring #1279 will otherwise reach for the `set -- "$@" --flag` idiom,
which is wrong here (see Alternatives A).

### 2. Bind five env vars on the runner container (both templates)

On `run-implementer.container.env` and `run-shepherd.container.env`, beside the
existing `WORKFLOW_NAME` entry rather than beside the CLI-driving
`WORKFLOW_SERVICE` / `WORKFLOW_SLUG` block — grouping them with the other
usage-correlation binding records the intent in the file's own structure:

```yaml
          # Optional Temporal / WorkItem correlation (gitops#1408, mirroring
          # gitops#1279 on cwft-mctl-agents-investigate.yaml). Read by the
          # usage producer (mctl-agents orchestrator/usage_ledger.py) next to
          # WORKFLOW_NAME above; NOT consumed by run_implementer's argv, which
          # has no such flags. Empty for every caller that does not set them.
          - name: WORKFLOW_WORK_ITEM_ID
            value: "{{workflow.parameters.work_item_id}}"
          - name: WORKFLOW_EXECUTION_ID
            value: "{{workflow.parameters.execution_id}}"
          - name: WORKFLOW_TEMPORAL_WORKFLOW_ID
            value: "{{workflow.parameters.temporal_workflow_id}}"
          - name: WORKFLOW_TEMPORAL_RUN_ID
            value: "{{workflow.parameters.temporal_run_id}}"
          - name: WORKFLOW_EXECUTION_REQUEST_ID
            value: "{{workflow.parameters.execution_request_id}}"
```

Env names are byte-identical to the investigate template's, because the
producer reads names, not templates.

Two consequences fall out for free and need no code:

- The fallback attempts (`implement-fallback`, the shepherd's account-2 retry)
  instantiate the same runner template, so they get the same env.
- The shepherd's in-pod implementer subprocess inherits the env, so
  review-fix usage records carry the same correlation as the tick that spawned
  them.

### 3. Deliberately no argv change

`run_implementer.py` and `run_shepherd.py` accept `--service`, `--slug`,
`--max-proposals` / `--dry-run` and nothing resembling `--work-item-id`.
Appending an unknown flag makes argparse exit 2 before any work — on **every**
run, including the cron sweep — so the argv-building block in both templates
stays byte-for-byte as it is. That non-change is the property the new test
pins, in the same spirit as gitops#1279's omit-both assertion: there, the
contract was "adding the flags must not change the omit case"; here it is
"adding the env must not change argv at all, for any value".

### 4. One new test, covering both templates

`tests/test_cwft_implement_shepherd_work_context_env.py`, following the
extract-don't-restate convention of
`tests/test_cwft_investigate_work_context_argv.py`,
`tests/test_cwft_shepherd_commit_pathspecs.py` and
`tests/test_tpl_git_commit_yq.py`:

- **Static half** (`yaml.safe_load` on each of the two CWFTs):
  the five parameters exist with `value` `""`; the pre-existing parameters keep
  their names and defaults; each of the five `WORKFLOW_*` names is bound
  exactly once on the runner template with the exact
  `{{workflow.parameters.<name>}}` value; none of the five placeholders occurs
  anywhere in `container.command`/`args`, `script.source` or an
  `initContainers` command of either file (a local, file-scoped restatement of
  the repo-wide validator, so this test fails on its own if someone "mirrors
  #1279 properly" and adds the flags).
- **Executable half**: slice each runner's argv region verbatim out of
  `container.args[2]` — from `set -- python -m orchestrator.run_implementer`
  (resp. `run_shepherd`) through the trailing `printf '\n'` — and run it under
  `/bin/sh`, asserting the echoed `→` line:
  - omit-all: the five vars unset → expected baseline argv;
  - omit-all-explicit: the five vars set to `""` → identical output;
  - set-all: benign values → identical output (this is the assertion that the
    env cannot leak into argv);
  - injection: values like `; touch <tmp>/pwned ;` and `a" ; id ; "b` →
    identical output and the sentinel file does not exist;
  - and, to prove the extracted slice is live rather than inert, the
    template's own parameters still work: `WORKFLOW_SERVICE` / `WORKFLOW_SLUG` /
    `WORKFLOW_MAX_PROPOSALS` (implement) and `WORKFLOW_DRY_RUN` (shepherd)
    produce the expected flags.
  Both slices are safe to run directly: neither invokes python or git inside
  the region between the markers (the real call is after `set +e`, outside the
  slice). Missing markers raise `AssertionError` rather than silently checking
  an empty string.

### 5. CI wiring

A `run: python3 tests/test_cwft_implement_shepherd_work_context_env.py` step in
`.github/workflows/validate-manifests.yml`, placed immediately after the
existing investigate step (lines 282-291), with a comment saying why: the
implement and shepherd argv is a cross-repo compatibility contract for the
cron sweep, `mctl_trigger_implementer` and the shepherd cron, and the env-only
rule is what keeps a hostile identifier out of a root pod holding the gitops
deploy key.

## Alternatives

**A. Mirror gitops#1279 literally, CLI flags included.** Attractive because the
diff would be a copy. Dropped: `run_implementer.py` / `run_shepherd.py` have no
such arguments, so argparse would exit 2 and every implement and shepherd run
would fail until a new `mctl-agents` release plus an `agent_image` bump landed
here — and the issue's own scope says "through env only". Partially adopting it
("add the flags but only when non-empty") is worse, not better: it hides the
breakage until the first DevLoop submit that actually sets a value, which is
the one submit nobody is watching a cron log for.

**B. Interpolate `{{workflow.parameters.temporal_workflow_id}}` straight into
the script body** (e.g. into the `printf` echo or an `export`). Dropped: Argo
substitutes into the *text* before `sh` parses it, so a crafted value executes
in a container that runs the Claude SDK with a write-capable deploy key and a
GitHub token — the exact class `scripts/validate-shell-param-interpolation.py`
exists to ratchet down. It would also fail CI immediately, since none of the
five names is in that script's `BASELINE` or `CONSTRAINED` sets.

**C. Let the runner derive the Temporal ids itself** (query Temporal, or
reconstruct `dev-loop-<owner>-<repo>-<n>` from the proposal's source issue).
Dropped: that is precisely the bug mctl-agents#461/#451 documents on the
investigator — a loop started by the execution-request dispatcher is
`dev-loop-xr_<id>`, so a derived id names a workflow that does not exist, and a
wrong correlation is worse than an absent one. It would also give the runner a
new dependency on Temporal reachability.

**D. One combined parameter (a JSON `work_context` blob).** Fewer parameters to
declare. Dropped: the producer reads five discrete `WORKFLOW_*` env names, so
the blob would have to be parsed somewhere in the pod — in shell, on
caller-supplied text, which is the injection surface B was rejected for — and
it would diverge from the investigate template that this issue explicitly asks
to mirror.

## Platform impact

**Migrations.** None. No persisted schema, no artifact shape, no committed file
depends on this. `.status.yaml` files, the Argo artifact handoffs and the
commit messages are untouched.

**Backward compatibility.** A submit that omits all five parameters gets:
identical argv (pinned by the new test), identical steps, identical commit
messages and identical incident fingerprints. The one observable difference is
that five env vars now exist on the runner pod with empty values, where before
they were absent. `cwft-mctl-agents-investigate.yaml` has shipped exactly that
shape since gitops#1279 and its usage records are correct, so the producer
already treats empty as absent; task 9 confirms it against one real record
post-merge instead of assuming. Argo accepts (and ignores) an unused parameter,
so nothing needs to change in mctl-api for existing callers.

**Rollout order.** Argo rejects a submit carrying a parameter the template does
not declare, so this change must merge and ArgoCD must sync (~3 min per
`CLAUDE.md`) before the `mctl-agents` DevLoop change starts sending the values.
That ordering is the reason this issue is the dependency of its sibling rather
than the other way round.

**Resource impact.** Five env vars per pod. Nothing else: no new volume, no new
container, no new secret, no change to requests/limits, mutexes,
`activeDeadlineSeconds` or the `mctl-gitops-main-writes` critical section.

**Risks and mitigations.**

- *A YAML slip in a 1157-line / 1569-line template* — e.g. an `env` entry
  landing on the wrong template, which `check_env_bindings` was written for
  after gitops#993. Mitigated by the static half of the new test (exact
  template, exact count), plus `yamllint` and the `kubeconform` step in
  `validate-manifests.yml`.
- *Someone later "completing the mirror" by adding the CLI flags* — the failure
  mode Alternative A describes. Mitigated by the no-placeholder assertion in
  the new test and by the explicit "NOT a CLI flag" comment on each parameter
  and on the env block.
- *A hostile identifier value* — mitigated structurally: the values only ever
  reach `env`, never an interpreted block, which both the repo-wide validator
  and the new injection cases check.
- *An unfiltered shepherd tick acting on several WorkItems while carrying one
  set of correlation values* — a caller-side concern (recorded as an open
  question in `requirements.md`); today's unfiltered cron tick passes nothing
  and is therefore unaffected.
- *Confusion between the two templates' identical-looking blocks* — mitigated
  by keeping the env names byte-identical on purpose and saying so in the
  comment, since the producer keys on names.
