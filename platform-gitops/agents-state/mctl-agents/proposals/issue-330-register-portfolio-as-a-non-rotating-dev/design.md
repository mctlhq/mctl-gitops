# Design: issue-330-register-portfolio-as-a-non-rotating-dev

## Current state

### One list gates everything

`config/settings.py` declares a single flat `SERVICES` list (lines 44-59) and a
`NON_ROTATING_SERVICES` set (lines 63-70). `ROTATING_SERVICES` is not written by
hand — it is derived:

```python
ROTATING_SERVICES = [s for s in SERVICES if s not in NON_ROTATING_SERVICES]
```

(`config/settings.py:77`). The module's header comment already documents this
pattern per service: `mctl-telegram` "is included as a valid
implementer/investigator target but is NOT a rotation service: it has no
`agents/<svc>/` scaffold and is driven only by GitHub-issue proposals via the
issue-investigator", and `mctl-academy`'s block spells out that registration
"is what lets `run_issue_poller.py` dispatch that issue at all (it skips issues
whose repo is not in `SERVICES`)". `seerrsense` — the precedent the issue cites
— appears in both collections (lines 57 and 69) and nowhere else in the repo:

```
config/settings.py:57:    "seerrsense",
config/settings.py:69:    "seerrsense",
```

That is the entirety of its registration.

### The two guards that reject `portfolio` today

1. **Poller.** `orchestrator/run_issue_poller.py` imports `SERVICES` (line 67)
   and partitions the labelled search results:
   `service_refs = [r for r in refs if r.repo in SERVICES]` /
   `other_refs = [...]` (lines 160-161). The per-issue loop recomputes
   `known_service = ref.repo in SERVICES` (line 201) and, when false, prints
   `WARN: {ref.repo} is not a known service (config/settings.py SERVICES) —
   skipping, label kept.`, increments `failures`, and `continue`s (lines
   218-224). `start_dev_loop_workflow` is never reached. The `--max-issues` cap
   is applied only to `service_refs`, so a `portfolio` issue today is pure noise
   in the failure count.
2. **Investigator.** `orchestrator/run_issue_investigator.py` imports `SERVICES`
   (line 71); `investigate()` sets `service = issue.ref.repo` and raises
   `SystemExit(f"Repo '{service}' is not a known service. Add it to
   config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no
   agents/<svc>/ scaffold) before investigating its issues.")` (lines
   1373-1379). The error message is itself the spec for this change.

The same `SERVICES` membership test appears in `run_implementer.py:1498`
(`--service` filter), `run_shepherd.py:2213`, `run_service_agent.py:84` and
`run_all.py:125`. All of them read the one list; none of them keeps a private
copy.

### Nothing downstream needs a per-service artefact

- **Temporal.** `orchestrator/temporal/` (start.py, workflows/, activities/)
  contains no service allowlist — `grep` for `SERVICES` across
  `orchestrator/temporal/*.py` returns nothing. `DevLoopWorkflow` derives its
  workflow id from the issue URL and hands the repo to the investigate CWFT; the
  gate is inside the driver, not the workflow.
- **Implementer scaffolding.** `_stage_implementer_agent`
  (`run_implementer.py:387-411`) looks for
  `agents/<service>/.claude/agents/implementer.md` and, when absent, falls back
  to `agents/_generic/.claude/agents/implementer.md` with an explicit
  `info: no per-service implementer for '<service>'; using generic fallback.`
  That file exists (`agents/_generic/.claude/agents/implementer.md`), so a
  scaffold-less service is a supported configuration, not an accident.
- **State directories.** `run_issue_investigator.py` creates what it needs:
  `service_dir.mkdir(parents=True, exist_ok=True)` in `_staging_dir` (line 270)
  and `proposal_dir.mkdir(parents=True, exist_ok=True)` (line 989, and line
  1569 for the parent). `agents-state/portfolio/` does not need to be
  pre-created in `mctl-gitops`.
- **Agent inventory.** `docs/agent-inventory.yaml` is keyed by AGENT
  (`issue-investigator`, `implementer`, `shepherd`, `incident-responder`,
  `service-agent`, `mentor`), not by service. `orchestrator/validate_manifest.py`
  only cross-checks inventory agent names against
  `agents/_manifests/*/agent.yaml` (`check_manifests_match_inventory`, line
  392+). There is no `seerrsense` entry to mirror, so per the issue's own
  conditional ("only if the inventory ... requires an entry per registered
  service"), the file stays untouched.

### The invariant that forces "both lists, not one"

`tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`
(lines 127-142) expands the service-agent's `agents/[!_]*/...` prompt globs and
asserts:

```python
assert matched == set(ROTATING_SERVICES)
```

`matched` is derived from directories on disk. Adding `"portfolio"` to
`SERVICES` alone would put it in `ROTATING_SERVICES` while no
`agents/portfolio/` directory exists, so this pre-existing test would fail —
a useful, load-bearing tripwire. Adding it to `NON_ROTATING_SERVICES` at the
same time keeps `ROTATING_SERVICES` byte-identical and the test green. There is
currently no test asserting `SERVICES`/`NON_ROTATING_SERVICES` membership
directly (`grep -rn "SERVICES" tests/` hits only `test_agent_inventory.py` and
`SHEPHERD_SKIP_SERVICES` in `test_run_shepherd.py`).

## Proposed solution

A config-only change plus one new test module. Three edits, in one commit.

### 1. `config/settings.py` — two list entries and a comment block

Append `"portfolio"` to `SERVICES` after `"seerrsense"` (before the commented-out
`# "upwork-mcp"` line), and add `"portfolio"` to `NON_ROTATING_SERVICES`.
Ordering in `SERVICES` is not semantically significant (every consumer does
membership tests or a full fan-out), but appending keeps the diff minimal and
matches how `seerrsense` was added.

Extend the module header comment — this file's established convention is that
every non-obvious registration carries a paragraph explaining *why* it is
non-rotating (see the `mctl-telegram`, `mctl-design` and `mctl-academy`
blocks). The new paragraph should state: `portfolio` is a static Astro site in
tenant `labs`, developed exclusively through the DevLoop; it has no
`agents/portfolio/` scaffold, so the rotation would fail immediately if it were
enrolled; its intake is human-labelled `agents:intake` issues, dispatched by
`run_issue_poller.py`.

### 2. `tests/test_settings.py` — a new membership test module

A small new file (there is no existing settings test to extend) asserting the
three facts the issue lists, plus the derivation that ties them together:

- `"portfolio" in SERVICES`
- `"portfolio" in NON_ROTATING_SERVICES`
- `"portfolio" not in ROTATING_SERVICES`
- `NON_ROTATING_SERVICES <= set(SERVICES)` — a general invariant, so a typo in
  either collection (`"portfolio"` vs `"portfolo"`) fails loudly instead of
  producing a silently inert entry. This generalises the specific bug class the
  change could introduce, rather than only pinning today's names.
- no duplicate entries in `SERVICES`.

Docstrings follow the house style visible in `tests/test_agent_inventory.py`:
say what drift the test exists to catch, not what the code does. `tests/` is
inside ruff's scope (`ruff check orchestrator config tests tools`) and outside
mypy's `files` (`pyproject.toml:137`), so the module needs `from __future__ import
annotations` ordering-clean imports but no annotations burden.

### 3. `docs/agent-inventory.yaml` — deliberately unchanged

Documented above and in requirements.md. Confirmed by reading the file: it has
no per-service section, and `seerrsense`/`mctl-pairdesk`/`mctl-academy` have no
entries. Touching it would create a false precedent that every service needs an
inventory row and would risk breaking
`test_agents_match_the_options_builders`, which asserts the inventory's agent
set equals the set of `build_*_options` functions.

### Resulting behaviour

- Poller: a `portfolio` issue labelled `agents:intake` lands in `service_refs`,
  is counted against `--max-issues`, and reaches `start_dev_loop_workflow`; on
  success the label is removed like any other handled issue.
- Investigator: `investigate()` proceeds past line 1373, resolves a slug under
  `agents-state/portfolio/proposals/`, and publishes the triplet plus a
  `.status.yaml` at `status: proposed`.
- Implementer: `--service portfolio` is accepted; `_stage_implementer_agent`
  logs the generic fallback.
- Rotation: `ROTATING_SERVICES` is unchanged, so `run_all._full()` and the daily
  CWFT fan-out are byte-identical to today.

## Alternatives

1. **Add `"portfolio"` to `SERVICES` only.** Fewest characters, and it does
   unblock the poller and investigator. Dropped: `ROTATING_SERVICES` is derived
   by subtraction, so the service would silently join the proactive rotation.
   `test_service_agent_scope_matches_rotating_services` fails immediately (no
   `agents/portfolio/` directory), and if that test were ever relaxed, the daily
   rotation would spawn a service-agent run that dies looking for
   `AGENTS_DIR/portfolio/CLAUDE.md`. The failing test is the good outcome here;
   the change is simply incomplete.

2. **Add `"portfolio"` to both lists AND scaffold `agents/portfolio/`
   (CLAUDE.md + context/ + researcher/analyst/spec-writer prompts), keeping it
   non-rotating for now.** Would make a later promotion into the rotation a
   one-line change. Dropped: the issue puts the scaffold explicitly out of
   scope, it is prompt surface that gets hashed into the service-agent's
   version (`docs/agent-inventory.yaml` `promptSources:
   agents/[!_]*/context/**`, `agents/[!_]*/CLAUDE.md`), and an unused-but-hashed
   scaffold would bump that agent's version for no behavioural reason. Worse,
   the `[!_]*` glob would then match `agents/portfolio/`, breaking the
   `matched == set(ROTATING_SERVICES)` assertion in the opposite direction.

3. **Replace the hard-coded lists with a data file (`config/services.yaml`) or
   with discovery from `agents/` on disk, so registering a service is a data
   change.** Attractive as a long-term shape — it would also let `mctl-api`
   consume the same source and close the enum-drift gap behind
   `mctl-api#274`. Dropped for this issue: it is a refactor touching six
   importers (`run_all`, `run_implementer`, `run_issue_investigator`,
   `run_issue_poller`, `run_mentor`, `run_service_agent`, `run_shepherd`) and a
   cross-repo contract, all to land a two-line registration. Recorded here as
   the natural follow-up rather than smuggled into a fix.

## Platform impact

**Migrations.** None. No schema, no state file, no gitops manifest.
`agents-state/portfolio/` is created on first investigate by
`mkdir(parents=True, exist_ok=True)`.

**Backward compatibility.** Additive. `ROTATING_SERVICES` is provably unchanged
(both collections gain the same name, and the derivation subtracts one from the
other), so the daily rotation, the mentor digest fan-out
(`run_mentor.py:95` joins `SERVICES` into prompt text — the string simply gains
one name) and every `--service` filter behave as before for existing services.
Callers that pass an unknown `--service` still get the same error, now with
`portfolio` in the "Available:" list.

**Resource impact.** Negligible in this repo. Downstream, each dispatched
`portfolio` issue costs one investigate CWFT run (~USD 3 budget cap via
`ISSUE_INVESTIGATOR_BUDGET_USD`) and, once approved, one implementer run
(~USD 3 via `IMPLEMENTER_BUDGET_USD`) plus shepherd ticks. The poller's
`--max-issues` cap now applies to `portfolio` issues too, which is the intended
behaviour: they become dispatchable work rather than permanently-failing noise.

**Risks and mitigations.**

- *Risk:* the change is made in `SERVICES` only and the rotation picks up a
  service with no scaffold. *Mitigation:* pre-existing
  `test_service_agent_scope_matches_rotating_services` fails on that exact
  mistake, and the new `tests/test_settings.py` asserts the intended end state
  positively.
- *Risk:* MCP-triggered operations with a `service` enum
  (`mctl_trigger_implementer`, `mctl_trigger_approve`) reject `portfolio`
  server-side until `mctl-api#274` lands, so an operator may read "registered"
  as "usable from every entry point". *Mitigation:* this is the same state
  `seerrsense` is in today; the unfiltered forms and the Temporal DevLoop path
  work. Called out in requirements.md's open questions and worth repeating in
  the PR description.
- *Risk:* the implementer authors code for a repo whose conventions it has never
  seen, using the generic sub-agent. *Mitigation:* both agents run with
  `setting_sources=["project"]` inside a clone of the target repo and are
  prompted to read its `CLAUDE.md`; adding one to `mctlhq/portfolio` is the
  supported lever and needs no change here.
- *Risk:* shepherd starts merging `portfolio` PRs before the repo has branch
  protection or CI. *Mitigation:* `SHEPHERD_SKIP_SERVICES` is an env-var opt-out
  set in the gitops CronWorkflow (`run_shepherd.py:317-330`) and can be flipped
  without touching this repo — noted as an open question, not resolved here.
- *Risk:* the running CWFT image lags the merge, so the poller still skips
  `portfolio` issues for a while. *Mitigation:* expected and out of scope — the
  release pipeline rolls the image; verify with one live labelled issue after
  the rollout.
