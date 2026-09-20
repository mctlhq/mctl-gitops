# Design: issue-1279-chore-agents-accept-optional-work-item-i

## Current state

### The template and its parameter surface

`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
is a `ClusterWorkflowTemplate` named `mctl-agents-investigate`. Its
`spec.arguments.parameters` block (lines 75-91) declares exactly three
parameters:

```yaml
  arguments:
    parameters:
      - name: issue_url
        value: ""
      - name: agent_image
        value: ghcr.io/mctlhq/mctl-agents:1.51.0
      - name: agent_version
        value: ""
```

`issue_url` is required-but-empty-defaulted (the guard is in the shell, not in
the schema). `agent_image` is the only one interpolated inline, and only into
`container.image` — never into shell text. `agent_version` is declared and
deliberately unread: "carried for the record only — not consumed by
run-investigator", the same wording all five `cwft-mctl-agents-*.yaml`
templates use.

`spec.entrypoint` is `investigate-issue`, a four-step template (lines 139-192):
`investigate` (template `run-investigator`), `investigate-fallback` (the same
`run-investigator` template on the account-2 OAuth key, gated by
`when: "{{steps.investigate.status}} != Succeeded"`), `commit` (template
`commit-and-push`), and `assert-produced`. Both attempts run with
`continueOn: {failed: true, error: true}`, which is why `assert-attempt` exists
at all.

### How the command line is built today

The `run-investigator` template's container is the `mctl-agents` image invoked
through `/entrypoint.sh sh -c <body>`. The relevant slice of that body is lines
329-342:

```sh
    # issue_url is required. Fail fast with a clear message rather
    # than letting argparse emit a terse usage error deep in logs.
    if [ -z "$WORKFLOW_ISSUE_URL" ]; then
      echo "❌ issue_url parameter is required" >&2
      exit 1
    fi
    # Read the param from env, NOT inline workflow.parameters
    # interpolation: a crafted value would otherwise be spliced into
    # the shell command. `set --` keeps it a single quoted token.
    set -- python -m orchestrator.run_issue_investigator \
      --issue-url "$WORKFLOW_ISSUE_URL"
    printf '→'
    printf ' %s' "$@"
    printf '\n'
```

and the invocation itself, lines 352-356, is deliberately not `exec` so that
the artifact collector downstream still runs on a crash:

```sh
    set +e
    "$@"
    RC=$?
    set -e
    echo "investigator exited ${RC}"
```

The single parameter reaches that body as an env var, declared at lines 490-495:

```yaml
    env:
      # Workflow param injected as an env var so the shell layer can
      # quote it safely. Direct workflow.parameters.* interpolation in
      # the script body is a shell-injection vector.
      - name: WORKFLOW_ISSUE_URL
        value: "{{workflow.parameters.issue_url}}"
```

This is an argv list that is *already* built with `set --` but has no
conditional append in it — every other agent template does. There is therefore
an established idiom to copy rather than invent.

### The idiom in the sibling templates

`cwft-mctl-agents-implement.yaml` (lines 406-420) and
`cwft-mctl-agents-shepherd.yaml` (lines 429-446) both do exactly the thing this
issue asks for, for `--service` / `--slug`:

```sh
    # Read params from env, NOT inline workflow.parameters interpolation
    # (Argo template syntax): a value like `; rm -rf /` would otherwise be
    # spliced straight into the shell command. Build argv via `set --`
    # so each flag/value pair is a separate, properly quoted token.
    set -- python -m orchestrator.run_implementer
    if [ -n "$WORKFLOW_SERVICE" ]; then
      set -- "$@" --service "$WORKFLOW_SERVICE"
    fi
    if [ -n "$WORKFLOW_SLUG" ]; then
      set -- "$@" --slug "$WORKFLOW_SLUG"
    fi
```

paired with `- name: service` / `value: ""` at the spec level and
`- name: WORKFLOW_SERVICE` / `value: "{{workflow.parameters.service}}"` in the
container's `env`. `cwft-mctl-agents-reconcile.yaml` (lines 248-259) is the
most compact statement of the same shape. The `[ -n "$VAR" ]` test is what
makes a value-carrying flag optional; `[ "$VAR" = "true" ]` is the separate
idiom reserved for boolean store-true flags such as `--dry-run`, and is not
applicable here.

### What enforces the env-var binding

`scripts/validate-shell-param-interpolation.py`, run in
`.github/workflows/validate-manifests.yml` (with `--selftest` first), scans
every `*.yaml` under `cluster-templates/` and fails on any
`{{workflow.parameters.X}}` or `{{inputs.parameters.X}}` appearing inside a
`script.source`, `container.command/args`, `script.command/args`, or an
`initContainers` command. It is described in its own docstring as "a ratchet,
not a clean bill of health": the `BASELINE` set records the sites that still
interpolate and the check fails on anything not in it. A second escape hatch,
`CONSTRAINED`, exempts parameters that mctl-api's operation registry constrains
with an anchored pattern or enum — a list that is explicitly "a claim that the
API rejects a value the shell would otherwise execute".

Two new parameters would be in neither set. That is precisely why the env-var
binding is not a stylistic preference here: inline interpolation would fail CI.

### The consumer's expected flag names

`platform-gitops/agents-state/mctl-agents/proposals/issue-267-feat-work-context-resume-investigator-fr/tasks.md`
task 10 names the CLI surface being added to `run_issue_investigator.py`:
`--work-item-id`, `--execution-id`, `--resume-from-execution-id`, `--surface`,
`--actor-kind`. Only the first two are in this issue's scope. That proposal's
`design.md` also records the idempotency property this design leans on for the
fallback attempt: a repeated `execution_id` "already in `_seen_execution_ids`"
is "a no-op (idempotent)".

## Proposed solution

Three edits to one file,
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`.
No other file in this repo changes except the test and its CI step.

### 1. Declare the two parameters

Append to `spec.arguments.parameters`, after `agent_version`:

```yaml
      - name: work_item_id
        value: ""
        # Optional. Canonical WorkItem id, minted by the caller (the dev-loop
        # control plane). Forwarded verbatim to run_issue_investigator.py as
        # --work-item-id and omitted entirely when empty. NOT defaulted to a
        # generated value: an invented id would bind the run to a WorkItem
        # that does not exist. Consumed by mctl-agents#267.
      - name: execution_id
        value: ""
        # Optional. Execution identity for THIS attempt, minted by the same
        # caller alongside work_item_id. Same omit-when-empty rule.
```

`value: ""` is what makes them optional in Argo: a submit that names neither
resolves both to the empty string, and the shell test below elides both flags.
A caller that passes an explicit `""` is indistinguishable from one that omits
the parameter, and that is intended — there is no third state to represent.

### 2. Bind them as environment variables

In the `run-investigator` template's `container.env`, beside the existing
`WORKFLOW_ISSUE_URL`:

```yaml
      # Same reasoning as WORKFLOW_ISSUE_URL above, and enforced by
      # scripts/validate-shell-param-interpolation.py: these names are in
      # neither its BASELINE nor its CONSTRAINED set, so interpolating them
      # into the script body below fails CI rather than merely being
      # discouraged.
      - name: WORKFLOW_WORK_ITEM_ID
        value: "{{workflow.parameters.work_item_id}}"
      - name: WORKFLOW_EXECUTION_ID
        value: "{{workflow.parameters.execution_id}}"
```

The `WORKFLOW_*` prefix matches `WORKFLOW_ISSUE_URL` here and
`WORKFLOW_SERVICE` / `WORKFLOW_SLUG` in the implement and shepherd templates.
It is deliberately not the `PARAM_*` prefix: `check_env_bindings()` in the
validator keys on `PARAM_*` inside a `script.source`, and this is a
`container.args` body, so borrowing that prefix would claim a check that does
not actually cover this site.

Because both the primary and the fallback step instantiate the *same*
`run-investigator` template, this one `env` block serves both attempts. No
change to the `investigate-issue` steps block is needed, and the fallback
receives the identical pair — see the Open questions in `requirements.md`.

### 3. Append the flags conditionally

Between the existing `set -- python -m orchestrator.run_issue_investigator
--issue-url "$WORKFLOW_ISSUE_URL"` and the `printf '→'` echo block:

```sh
    # Optional work-context identifiers (gitops#1279). Appended only when
    # the caller supplied them, so a submit that omits both produces the
    # exact argv this template produced before they existed — which is what
    # keeps the change inert until mctl-agents#267 ships the flags and
    # mctl-api#335 lets a submit carry the parameters. No default is
    # invented for either: an empty value means absent, not "derive one".
    if [ -n "$WORKFLOW_WORK_ITEM_ID" ]; then
      set -- "$@" --work-item-id "$WORKFLOW_WORK_ITEM_ID"
    fi
    if [ -n "$WORKFLOW_EXECUTION_ID" ]; then
      set -- "$@" --execution-id "$WORKFLOW_EXECUTION_ID"
    fi
```

Placement matters in both directions. It must be *after* the `set --` that
seeds argv (otherwise `"$@"` is not yet the command) and *before* the
`printf ' %s' "$@"` echo (so the archived step log shows the resolved command
line an operator will be asked about), and it must never appear after the
`set +e; "$@"` invocation. `--issue-url` stays first and unconditional: it is
still required and still guarded by the existing `[ -z "$WORKFLOW_ISSUE_URL" ]`
fail-fast above.

Ordering between the two new flags is fixed (`--work-item-id` then
`--execution-id`) only so the test can assert on an exact argv; argparse does
not care.

### 4. Lock the behaviour with an extracted test

Add `tests/test_cwft_investigate_work_context_argv.py`, following the
convention of `tests/test_tpl_git_commit_yq.py` and
`tests/test_rotate_github_token_scope.py`: load the CWFT with `yaml.safe_load`,
slice the argv-building region out of the `run-investigator` template's
`container.args[2]` **verbatim** (from the `if [ -z "$WORKFLOW_ISSUE_URL" ]`
guard through the trailing `printf '\n'`), and run that slice under `/bin/sh`
with the three env vars set. The slice never invokes python — the actual call
happens later in the body, after `set +e` — so it is safe to execute directly
and its stdout is exactly the `→ ...` echo line.

Extracting rather than restating is the point those two existing tests make in
their own docstrings: "a copy would keep passing after the template changed,
which is the failure mode this file exists to avoid". Wire it into
`.github/workflows/validate-manifests.yml` as a `python3 tests/…py` step,
mirroring the existing "Unit-test the release-deploy bump script" step.

## Alternatives

**A. Interpolate `{{workflow.parameters.work_item_id}}` directly into the shell
body.** Fewer lines, no env block. Rejected outright:
`scripts/validate-shell-param-interpolation.py` fails the PR, since neither
name is in `BASELINE` (which the script's docstring says must "go down and
never up") nor in `CONSTRAINED`. Even if it passed, this container holds
`GITHUB_TOKEN`, an SSH-cloned gitops worktree, and the Claude SDK agent's Bash
grant — the template's own comment at line 335 already names this exact shape
as the vector it is avoiding.

**B. Pass the identifiers as environment variables only, with no CLI flags at
all** — the `cwft-mctl-agents-run.yaml` idiom, where `RUN_MODE` / `RUN_SERVICE`
are read straight out of `os.environ` by `orchestrator.run_all` and no flag is
built. This is a genuine in-repo precedent and would be marginally simpler on
this side. Rejected because the consumer has already chosen its interface:
`mctl-agents#267` task 10 specifies `--work-item-id` and `--execution-id` as
argparse flags with cross-flag validation (`--resume-from-execution-id` without
`--work-item-id` exits non-zero). Shipping an env-only contract here would
force a second contract on the other side of the boundary this issue exists to
close, and the issue's own scope says "threaded through … as the corresponding
flags".

**C. Always append the flags, passing an empty string when unset** —
`--work-item-id "" --execution-id ""`. Drops both `if` blocks. Rejected against
two of the issue's three acceptance criteria at once: the command line for a
submit omitting both would no longer be "unchanged from today", and
`run_issue_investigator.py` would receive `""` rather than `None`, which is an
invented value in everything but name. It also pushes the "is this absent?"
decision across the repo boundary into Python, where it becomes invisible to
the `→` echo line an operator reads in the step log.

**D. Declare the parameters but leave them unconsumed**, matching
`agent_version`'s "carried for the record only" treatment. Rejected because it
satisfies scope item 1 and fails scope item 2 — the identifiers would appear on
the submit, be visible in the Argo UI, and still never reach the script, which
is a worse failure than not accepting them at all: it looks wired.

## Platform impact

**Migrations.** None. No CRD, no schema, no stored state. ArgoCD reconciles the
`ClusterWorkflowTemplate` from this repo; per `CLAUDE.md`, allow ~3 minutes
after merge before submitting, because Argo snapshots the template at submit
time and a submit issued during that window runs the old definition.

**Backward compatibility.** Exact for every existing caller. The two new
parameters default to `""`; both `if` blocks elide; argv is byte-identical to
today's for `mctl_trigger_issue`, a hand-submitted `Workflow`, and the
DevLoopWorkflow path. Argo does not require a submit to enumerate a
`ClusterWorkflowTemplate`'s parameters, so no caller needs updating. The `→`
echo in the step log is the on-the-spot proof of this for any given run.

**Cross-repo sequencing.** Two ordering constraints, in opposite directions:

- *Forward.* This change is not usable until `mctlhq/mctl-api#335` lets the
  operation registry accept the two parameters; until then a submit carrying
  them is rejected before it reaches Argo. Landing this first is correct — it
  is the prerequisite the consumer's proposal named — and is harmless while it
  waits.
- *Backward, and the real risk.* The moment a caller *can* pass the values,
  the flags reach whatever `run_issue_investigator.py` is inside the pinned
  `agent_image` (today `ghcr.io/mctlhq/mctl-agents:1.51.0`). argparse exits 2
  on an unrecognised flag, so passing `--work-item-id` to an image predating
  `mctl-agents#267` fails the attempt — then fails the account-2 fallback for
  the same reason, burning both OAuth attempts — and `assert-attempt` reports
  the run Failed. Mitigation: the `agent_image` default pin must be bumped to
  the mctl-agents release containing the flags **before** any caller passes
  them, and that bump is a separate commit deliberately not made here. The
  template already carries the precedent for this style of guard in its
  `run-investigator` header comment ("pin >=1.11.0; earlier tags lack the
  module and crash with ImportError"); the new parameter comments should say
  the same thing about these flags. Note the failure is loud and attributable
  (argparse usage error in the step log, visible on the `→` line immediately
  above it), not silent.

**Security.** Neutral-to-positive. Both values are bound through `env:` and
appended as separate `set --` tokens, so a value carrying `;`, a quote, or a
newline is one argv element and never shell text — the same property
`--issue-url` already has. Neither value becomes a filesystem path, a git ref,
a pathspec, or part of a JSON body in this template, so the path-component
sanitising that `cwft-mctl-agents-approve.yaml` applies to `service`/`slug`
(lines 189-200) has no analogue to enforce here. The artifact collector's
`ALLOWED` regex and `commit-and-push`'s scope guards are untouched, so the
blast radius of the commit step is unchanged. No new secret, mount, or
NetworkPolicy selector.

**Resource impact.** None. No new step, container, volume, or artifact; two
environment variables on an existing pod.

**Risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| Flags reach an `agent_image` that does not know them; both attempts fail | Bump the pin before any caller passes values; the failure is a loud argparse usage error next to the `→` echo, not a silent wrong result |
| Someone later "simplifies" the two `if` blocks into unconditional flags | The extracted test asserts the omit-both case produces the exact current argv, and fails on that edit |
| Someone later inlines `{{workflow.parameters.work_item_id}}` into the shell | `scripts/validate-shell-param-interpolation.py` fails the PR — the names are in neither `BASELINE` nor `CONSTRAINED`, by design |
| The fallback attempt reusing the caller's `execution_id` is read as a forked execution | `mctl-agents#267`'s design makes a repeated `execution_id` an idempotent no-op; recorded as an open question rather than resolved unilaterally here |
| Template edited but submitted before ArgoCD syncs; the run silently uses the old spec | Wait ~3 min per `CLAUDE.md`; confirm via the `→` line in the archived step log, reachable with `mctl_get_workflow_logs` |

**Rollback.** Reverting the single commit restores the previous template
exactly; because no caller can have depended on the parameters until
`mctl-api#335` ships, a revert cannot strand one. See `tasks.md`.
