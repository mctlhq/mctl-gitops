# Design: issue-533-register-newton-mcp-gateway-as-a-non-rot

## Current state

### The single registry

`config/settings.py` holds three collections, all derived from one another:

- `SERVICES` (lines 61-78) — a hand-maintained list of 15 repo names. A long
  comment block (lines 9-60) precedes it, with one paragraph per entry whose
  presence is non-obvious: `mctl-agents`, `mctl-telegram`, `mctl-design`,
  `mctl-academy`, `portfolio`, `.github`. Two entries (`mctl-pairdesk`,
  `seerrsense`) have no paragraph. The list also carries one commented-out
  entry, `# "upwork-mcp"`.
- `NON_ROTATING_SERVICES` (lines 82-91) — a `set` of 8 names: valid
  implementer/investigator targets that the proactive rotation must skip.
- `ROTATING_SERVICES` (line 98) — `[s for s in SERVICES if s not in
  NON_ROTATING_SERVICES]`, i.e. purely derived. Today it is the 7 repos that
  actually have an `agents/<svc>/` scaffold on disk: `mctl-web`,
  `mctl-openclaw`, `mctl-docs`, `mctl-api`, `mctl-portal`, `mctl-agent`,
  `mctl-gitops`.

### The two gates the issue names

1. **`orchestrator/run_issue_poller.py`** imports `SERVICES` (line 67) and
   uses it three times: to partition the search results into `service_refs` /
   `other_refs` (lines 168-169, so the `--max-issues` cap applies only to
   dispatchable issues), for the dry-run preview (lines 213-221), and for the
   live skip at lines 224-231 which prints
   `WARN: <repo> is not a known service (config/settings.py SERVICES) —
   skipping, label kept.` and does `failures += 1`. The label is deliberately
   left so the operator notices. A registered repo instead reaches
   `start_dev_loop_workflow(ref.url, client=client)` (line 234), whose
   workflow id is `dev-loop-{owner}-{repo}-{issue}`.

2. **`orchestrator/run_issue_investigator.py`** imports `SERVICES` (line 76)
   and gates at lines 2457-2464:
   `service = issue.ref.repo; if service not in SERVICES: raise SystemExit(...)`.
   The message already tells the operator exactly what to do — "Add it to
   config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no
   agents/<svc>/ scaffold)". Immediately after the gate, line 2466 derives
   `proposals_dir = state_dir / service / "proposals"`, and the directory is
   created lazily with `mkdir(parents=True, exist_ok=True)` (lines 1276, 2823,
   and `service_dir.mkdir(...)` at line 425) — so no state directory has to be
   pre-created in mctl-gitops.

### Every other consumer of the registry

Grepping `SERVICES` across `orchestrator/` shows the full blast radius of
appending one name:

- `orchestrator/run_implementer.py:140,4663,4721-4722` — `--service` filter
  validation and its help text. Line 1726-1733 is the scaffold fallback:
  `AGENTS_DIR / service / ".claude" / "agents" / "implementer.md"`, and if it
  does not exist, `agents/_generic/.claude/agents/implementer.md`. This is
  precisely the mechanism that lets a scaffold-less service be implemented;
  line 4513 documents it in so many words.
- `orchestrator/run_all.py:21,117,128-131` — `_full()` iterates
  `ROTATING_SERVICES`, not `SERVICES`, so a non-rotating entry is never
  scheduled for a proactive run. The `--service` one-shot validates against
  `SERVICES`.
- `orchestrator/run_service_agent.py:15,181,185` — validates against
  `SERVICES` and then reads the on-disk scaffold. A manual
  `run_service_agent --service newton-mcp-gateway` would therefore pass
  validation and then fail on the missing scaffold. That is exactly the
  pre-existing behaviour for `portfolio`, `seerrsense`, `.github` and every
  other non-rotating entry; it is not a new failure mode.
- `orchestrator/pr_adoption.py:35,484,756` — iterates
  `sorted(repos & set(SERVICES))` when adopting orphan PRs, so the new entry
  widens that intersection by one repo.
- `orchestrator/run_mentor.py:13,95` — `services_list = ", ".join(SERVICES)`
  is interpolated into the mentor prompt, so the mentor's rendered prompt
  text gains one name.
- `orchestrator/run_shepherd.py:3881` — `--service` validation. The shepherd's
  per-service policy sets (`SHEPHERD_SKIP_SERVICES`,
  `SHEPHERD_FIX_ONLY_SERVICES`, lines 566-567) are env-derived and
  `NEVER_MERGE_SERVICES` (line 627) is the code constant
  `{"mctl-academy", "mctl-gitops", ".github"}`. None of them is touched, so
  `newton-mcp-gateway` lands in the shepherd's default full mode — which is
  what the issue asks for.

### What does NOT need to change

- **`docs/agent-inventory.yaml`.** It is keyed per AGENT (`implementer`,
  `service-agent`, `issue-investigator`, ...), not per service. `portfolio`,
  `seerrsense` and `mctl-pairdesk` appear nowhere in it — a full-repo grep for
  `portfolio` outside CHANGELOG.md hits only `config/settings.py`,
  `tests/test_settings.py` and incidental prose in `run_implementer.py`,
  `run_shepherd.py`, `subagent_wait.py`. The inventory's service coupling is
  its `agents/[!_]*/...` promptSources globs, which are derived from disk;
  `tests/test_agent_inventory.py:128-142`
  (`test_service_agent_scope_matches_rotating_services`) asserts those globs
  equal `set(ROTATING_SERVICES)`. Since this change leaves `ROTATING_SERVICES`
  untouched and creates no `agents/newton-mcp-gateway/` directory, that
  assertion keeps holding. Nothing in `orchestrator/validate_manifest.py` or
  `agents/_manifests/` is per-service either.
- **`config/settings.py` is not a prompt source** for any agent in the
  inventory, so appending to `SERVICES` does not bump any agent's version
  hash in the registry (`tools/publish_agent_release.py`).
- **README.md / LLMS.md** — neither documents the service registry or a
  registration procedure (grep for `config/settings.py`, `NON_ROTATING`,
  `known service` returns nothing in either file).

## Proposed solution

A three-file change, deliberately minimal, following the `portfolio` (#331)
and `.github` (#371) precedents exactly.

### 1. `config/settings.py` — two list/set appends plus one comment paragraph

Append a paragraph to the comment block, after the `.github` paragraph that
ends at line 60 and before `SERVICES = [`:

> `newton-mcp-gateway` is a private Python/uv MCP server in tenant `labs`,
> developed exclusively through the DevLoop (epic
> `mctlhq/newton-mcp-gateway#1`). Registered here so `run_issue_poller.py` will
> dispatch its `agents:intake` issues at all — it skips any issue whose repo is
> not in `SERVICES`. It has no `agents/newton-mcp-gateway/` scaffold, so it must
> NOT enter `ROTATING_SERVICES`: the proactive researcher/analyst/spec-writer
> rotation reads `AGENTS_DIR / <service> / CLAUDE.md` and would fail
> immediately. The generic implementer sub-agent
> (`agents/_generic/.claude/agents/implementer.md`) covers it. Its PRs stay
> shepherd-owned — no `SHEPHERD_SKIP_SERVICES` entry.

Then add `"newton-mcp-gateway",` to `SERVICES` (after `".github",`, before the
commented-out `# "upwork-mcp"` line, so the live entries stay contiguous) and
`"newton-mcp-gateway",` to `NON_ROTATING_SERVICES`.

`ROTATING_SERVICES` needs no edit — it is derived, and the two appends cancel
out by construction. That derivation is the reason this change is two lines
and not a third list.

### 2. `tests/test_settings.py` — two tests mirroring the `.github` pair

Follow the existing shape (`test_dot_github_is_a_registered_service` /
`test_dot_github_is_non_rotating`, lines 35-48) rather than inventing a new
one, so the file stays a flat list of one-assertion-per-fact tests:

```python
def test_newton_mcp_gateway_is_a_registered_service():
    """mctlhq/newton-mcp-gateway must be a valid implementer/investigator target."""
    assert "newton-mcp-gateway" in SERVICES


def test_newton_mcp_gateway_is_non_rotating():
    """No agents/newton-mcp-gateway/ scaffold, so it must stay out of the rotation."""
    assert "newton-mcp-gateway" in NON_ROTATING_SERVICES
    assert "newton-mcp-gateway" not in ROTATING_SERVICES
```

The docstrings carry the *why*, matching the file's own convention and its
module docstring ("A service added to one without the other either breaks the
rotation ... or silently drops a valid implementer target").

Three existing tests in the same file already cover the derived invariants and
need no edit: `test_non_rotating_services_are_all_registered`
(`set(NON_ROTATING_SERVICES) <= set(SERVICES)`),
`test_services_has_no_duplicates`, and
`test_no_service_name_is_shell_glob_hostile_beyond_a_leading_dot` (the new
name has no `/` and is not `.`/`..`, so it passes).

### 3. `docs/agent-inventory.yaml` — left untouched

Per the investigation above, the conditional in the issue resolves to "no
entry required". The implementer should verify this by re-running
`uv run --locked pytest tests/test_agent_inventory.py` after the settings
change and confirming it is green, rather than taking this design's word for
it.

### Why this way

The registry is deliberately one hand-maintained list with a comment block
that explains every non-obvious member, and a derived rotating subset. The
alternative designs below all trade that legibility for machinery this repo
does not need at 15 services. Appending to the list, and pinning the
membership with a test that states the reason in its docstring, is the shape
the codebase already chose three times (#320, #331, #371) and is the shape the
next reader will expect.

## Alternatives

1. **Derive `SERVICES` from disk (`agents/*/`) plus a non-rotating overlay.**
   Rejected: it inverts the current semantics. Today `agents/<svc>/` existence
   *implies* rotating, and `SERVICES` is the superset that includes
   scaffold-less DevLoop targets. Deriving the superset from disk would
   require creating an empty `agents/newton-mcp-gateway/` marker directory —
   exactly what the issue puts out of scope — and would break
   `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`,
   whose whole premise is that the on-disk glob equals `ROTATING_SERVICES`.

2. **Make the registry a YAML/JSON config file loaded at import.** Rejected as
   scope creep and as a net legibility loss. The comment block at
   `config/settings.py:9-60` is the actual documentation of why each service is
   registered and why it rotates or does not; moving it to data would either
   lose that prose or reproduce it as YAML comments nobody reads. It would also
   touch every one of the eight importing modules, turning a two-line change
   into a refactor with a much larger review surface — for a list that grows
   roughly quarterly.

3. **Register in `SERVICES` only, and skip `NON_ROTATING_SERVICES`.**
   Rejected: it is the failure mode `tests/test_settings.py` exists to catch.
   Omitting the non-rotating entry puts `newton-mcp-gateway` into the derived
   `ROTATING_SERVICES`, which `orchestrator/run_all.py:117` iterates for the
   weekly rotation; `run_service_agent.py` would then look for
   `agents/newton-mcp-gateway/CLAUDE.md`, not find it, and fail on every
   scheduled run. It would also break
   `test_service_agent_scope_matches_rotating_services`, since the disk globs
   would no longer equal the list.

4. **Add a `SHEPHERD_SKIP_SERVICES` entry alongside, "to be safe".** Rejected:
   explicitly out of scope per the issue — the shepherd is meant to own this
   repo's PRs. Adding it would silently move review/fix/merge to a pr-steward
   that is not configured for this repo, i.e. no owner at all.

## Platform impact

**Migrations.** None. No schema, no state-file format, no stored data. The
`agents-state/newton-mcp-gateway/` tree is created on first use by
`mkdir(parents=True, exist_ok=True)`.

**Backward compatibility.** Additive. Every existing service keeps its exact
behaviour; `ROTATING_SERVICES` is byte-identical before and after, so no
proactive schedule, no agent version hash, and no inventory glob changes.

**Resource impact.** Negligible and bounded. `run_issue_poller` gains at most
one more dispatchable repo per cycle, still under the `DEFAULT_MAX_ISSUES = 5`
cap. `pr_adoption.py`'s `repos & set(SERVICES)` intersection widens by one.
Each dispatched issue costs one investigator run (~$3) plus whatever the
implementer and shepherd spend — the normal per-issue DevLoop cost, incurred
only when a human applies the `agents:intake` label.

**Risk: the private-repo token.** The highest-probability way this change
looks broken after merge is not the code. `newton-mcp-gateway` is private, so
`gh search issues --owner mctlhq` in `search_labeled_issues()` must return its
issues under the poller's `GITHUB_TOKEN`, and
`_clone_repo` (`run_issue_investigator.py:1113-1150`) must succeed on
`gh repo clone mctlhq/newton-mcp-gateway`. *Mitigation:* before relying on the
cron, confirm with `python -m orchestrator.run_issue_poller --dry-run` against
a labelled `newton-mcp-gateway` issue — it is side-effect-free (no workflow
start, no relabel) and its output distinguishes "not a known service" (code
problem, now fixed) from an empty search result (token/installation problem,
fixed in GitHub App settings, not in this repo).

**Risk: mctl-api's `service` enum lags.** The operator-facing MCP tools
(`mctl_trigger_approve`, `mctl_trigger_implementer`, `mctl_trigger_reconcile`,
`mctl_trigger_shepherd`) carry a hard-coded `service` enum that will reject
`newton-mcp-gateway` until the mctl-api change lands
(`mctlhq/mctl-api#274`). *Mitigation:* none needed here — the poller →
DevLoopWorkflow → implementer path does not traverse that enum; only manual
per-service operator filters do. An operator who needs one before #274 can
omit the `service` filter and use `slug` instead, which is not enumerated.

**Risk: rollout timing.** The change only takes effect once the CronWorkflow /
CWFT images are rebuilt with the new commit. *Mitigation:* explicitly out of
scope (the release pipeline handles it); until then the poller keeps the label
and retries next cycle, which is the designed behaviour — nothing is lost.

**Risk: shepherd merges into a brand-new repo.** `newton-mcp-gateway` is not
in `NEVER_MERGE_SERVICES` (`run_shepherd.py:627`), so the shepherd may merge
its PRs autonomously once they pass review. This is intended per the issue's
out-of-scope note. *Mitigation:* if the repo needs a human gate during
bring-up, that is a `SHEPHERD_MERGE_APPROVAL_SERVICES` env change in the
gitops CronWorkflow (`run_shepherd.py:575`), not a code change here — flagged
for the reviewer rather than pre-empted.
