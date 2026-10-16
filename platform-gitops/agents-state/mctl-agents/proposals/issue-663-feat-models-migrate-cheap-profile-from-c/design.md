# Design: issue-663-feat-models-migrate-cheap-profile-from-c

## Current state
- `config/model-policy.yaml` (version 1) defines two profiles:
  - `cheap`: `model: claude-haiku-4-5`, `model_env: CLAUDE_CHEAP_MODEL`
  - `balanced`: `model: claude-sonnet-5-5`, `model_env: CLAUDE_BALANCED_MODEL`

  Its `tasks:` map `service_agent`, `mentor_digest` and `review_findings_normalize`
  all to `balanced`. The inline comment records why the last two left `cheap` on
  2026-10-01 (gitops#1058, guessed root causes in the incident responder). It also
  records that `cheap` "stays defined for purely mechanical tasks".
- `config/model_policy.py`: `ModelPolicy.resolve()` uses this precedence:
  1. the task's legacy env var (`SERVICE_AGENT_MODEL`, `MENTOR_MODEL`, `SHEPHERD_MODEL`)
  2. the profile's `model_env`
  3. the YAML default

  `ModelPolicy.load()` honours `MODEL_POLICY_PATH`. `resolve_model()` is the module
  entry point.
- `config/settings.py` resolves `SERVICE_AGENT_SELECTION`, `MENTOR_SELECTION` and
  `SHEPHERD_SELECTION` at import time. `orchestrator/resolver.py::execute()` resolves
  `profile.model_policy_task` from the v1alpha2 catalog.
  `orchestrator/validate_manifest.py` checks that manifest and catalog tasks exist in
  the policy.
- Manifests (`agents/_manifests/{authoring-canary,implementer,incident-responder,service-agent}`)
  use task `service_agent`, `mentor` uses `mentor_digest`, and `shepherd` uses
  `review_findings_normalize`. Nothing resolves to `cheap` today.
- `.env.example:31` has `CLAUDE_CHEAP_MODEL=claude-haiku-4-5`.
- `tests/test_model_policy.py` builds a synthetic `ModelPolicy` (with `cheap-default`
  and `balanced-default`). No test loads the committed YAML and asserts its
  defaults or routing.
- `claude-haiku-4-5` reference inventory (`grep -rn`, `.git` excluded):
  - `config/model-policy.yaml:5`: active default. Migrate.
  - `.env.example:31`: active default. Migrate.
  - `CHANGELOG.md:1401-1402`: historical release notes. Preserve.
  - `docs/benchmarks/capability-discovery.md:71`: records which model the CLI's side
    calls used in a past measured run. Historical. Preserve.
  - `tests/fixtures/model-usage-records.json` (`claude-haiku-4-5-20251001`): a
    usage-ledger record of a past reviewer run. Historical. Preserve.
  - `tests/test_usage_ledger.py:36` (`HAIKU = "claude-haiku-4-5-20251001"`): an
    arbitrary second model key for ledger aggregation tests. It does not stand for
    the current default. Preserve.
- The SDK is `claude-agent-sdk==0.2.163` (`pyproject.toml`, `uv.lock:154`). Its
  bundled CLI is the harness, per the `Dockerfile` comments at lines 10-16.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`:
  - Does not set `CLAUDE_CHEAP_MODEL`; a grep found no occurrence.
  - `INCIDENT_RESPONDER_MODEL` is deliberately unset.
  - A comment at around line 510 records that it "used to pin claude-haiku-4-5" and
    was moved off it for judgement reasons.
  - Conclusion: the deployed runs pick up the YAML default for `cheap`, but no
    deployed task routes to `cheap`.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/{mentor-default,shepherd-default}/profile.yaml`:
  `modelPolicyRef` tasks are `mentor_digest` and `review_findings_normalize`. Both
  are balanced in this repo.
- `$MCTL_GITOPS_ROOT/agent-platform/policy.yaml:87`: `knownModelPolicyTasks` exists.
  It is unchanged because no task is added.
- `$MCTL_GITOPS_ROOT/services/labs/claude-remote/values.yaml:105-111`:
  - A separate service already runs `CLAUDE_REMOTE_MODEL: "claude-haiku-5-5"` (since
    2026-10-10).
  - It notes the id needs Claude Code 2.1.296+ (image 0.13.4+), and that 2.1.280 does
    not know it.
  - This is evidence that the id exists, and a warning about the CLI version.
- Not observed: the CLI version bundled in `claude-agent-sdk==0.2.163`. It is not
  recorded in the clone, so it is listed under Open questions. MCP service tools were
  not needed, because mctl-agents runs as Argo CWFTs whose env is in the gitops file
  above.

## Proposed solution
1. **Default flip.**
   - In `config/model-policy.yaml`, set `cheap.model: claude-haiku-5-5`, keeping
     `model_env: CLAUDE_CHEAP_MODEL`.
   - Extend the existing `tasks:` comment by one line. It should say that the
     2026-10-16 move to Haiku 5.5 changes only the cheap default, and that routing
     any task to `cheap` needs a separate evaluation.
   - In `.env.example`, set `CLAUDE_CHEAP_MODEL=claude-haiku-5-5`. Add a one-line
     comment, in the file's existing Russian comment style or in English, naming
     `claude-haiku-4-5` as the rollback value.
2. **Tests on the committed policy.** Add tests to `tests/test_model_policy.py` that
   use `ModelPolicy.load(DEFAULT_POLICY_PATH)`, with `MODEL_POLICY_PATH`,
   `CLAUDE_CHEAP_MODEL`, `CLAUDE_BALANCED_MODEL` and the legacy env vars cleared
   through `monkeypatch.delenv(..., raising=False)`:
   - The committed `cheap` profile resolves to `claude-haiku-5-5` from source
     `policy`. No committed task is bound to `cheap`, so the test resolves through a
     policy built from the loaded document's `profiles` plus a synthetic
     `probe: cheap` task. Alternatively it asserts directly on the parsed YAML
     profile. This keeps the production `tasks:` map untouched.
   - The routing boundary: the three committed tasks resolve to `balanced` /
     `claude-sonnet-5-5`, and no committed task maps to `cheap`. This is the guard
     against silent re-routing.
   - Rollback: with `CLAUDE_CHEAP_MODEL=claude-haiku-4-5`, the probe resolves to
     `claude-haiku-4-5` with source `CLAUDE_CHEAP_MODEL`.
   - The existing synthetic tests stay as they are.
3. **Provider smoke check.** Add an opt-in script, `tools/model_smoke.py`. It:
   - resolves the `cheap` profile model through `config.model_policy` (honouring
     `CLAUDE_CHEAP_MODEL`, so the same script also proves the rollback);
   - runs one `claude_agent_sdk.query` with that model, `max_turns=1` and no tools,
     using the pinned SDK and its bundled CLI;
   - asserts that the result is not an error and that the model key reported in the
     result's usage matches the requested id;
   - prints the model, tokens, duration and cost.

   It is not collected by pytest and is not run in CI. If it fails on the current
   pin, bump `claude-agent-sdk` in `pyproject.toml` and `uv.lock` to the lowest
   release whose bundled CLI accepts the id (2.1.296 or later, according to the
   claude-remote note) and re-run.
4. **Bounded evaluation.** Add `docs/benchmarks/haiku-5-5-cheap-profile.md` with a
   small reproducible comparison: N=10 fixed inputs on each of two mechanical tasks.
   - Task 1: classify a fixed set of conventional-commit subjects into `type`, as
     JSON.
   - Task 2: extract `{repo, number}` from fixed PR/issue URLs, as JSON.
   - Run both models with the same prompts, using an `--eval` mode of the smoke
     script or a sibling script in `tools/`.
   - Record:
     - correctness against the expected answers;
     - the malformed-JSON rate;
     - p50 and max latency;
     - input/output tokens;
     - the CLI-reported cost (the harness reports `costUSD`; it does not compute USD
       itself, as in `capability-discovery.md`).
   - State explicitly that this is no evidence for moving judgement tasks.
5. **Audit record.** Put the reference inventory from Current state into the benchmark
   note, or into the PR body, as the "historical, preserved" list. Leave all four
   historical references unchanged.

Why this way: it is the smallest change that meets every acceptance criterion
without reworking the schema. The new tests pin both the new default and the safety
boundary against the committed file, which the synthetic test does not.

## Alternatives
- **Change only the env default in gitops (set `CLAUDE_CHEAP_MODEL` in the CWFT).**
  Dropped. It leaves the repo default stale, puts the source of truth in two places,
  and the issue explicitly wants the YAML default changed.
- **Use the floating `haiku` alias instead of the pinned id.** Dropped. The
  claude-remote change pinned the full id on purpose so the model cannot drift with
  the CLI's alias table, and the policy already uses full ids.
- **Bind a real mechanical task to `cheap` so the smoke test runs a production
  agent.** Dropped. That is a routing change, which the issue puts out of scope and
  says needs a separate evaluation.

## Platform impact
- Migrations: none. There are no schema or data changes, and historical ledger
  records stay unchanged.
- Runtime: no production run changes model, because no task resolves to `cheap`.
  Deployed CWFTs do not set `CLAUDE_CHEAP_MODEL`, so the new default takes effect
  for any future cheap-bound task as soon as the image rolls.
- Backward compatibility: the `CLAUDE_CHEAP_MODEL` override and the legacy per-task
  env vars keep their current precedence.
- Risks and mitigations:
  - The bundled CLI does not know `claude-haiku-5-5`, so a future cheap task fails
    at runtime. Mitigation: the smoke check gates the PR, and the SDK is bumped if
    needed.
  - An SDK bump changes the harness for all agents. Mitigation: bump only if
    required, and call it out in the PR.
  - Someone later reads this PR as permission to move judgement tasks. Mitigation:
    the routing-boundary test and the policy comment.
- Resource and cost impact: negligible. The smoke check and the evaluation are
  one-off manual spends of under about $1.
