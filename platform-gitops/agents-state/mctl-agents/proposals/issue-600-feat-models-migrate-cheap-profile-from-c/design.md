# Design: issue-600-feat-models-migrate-cheap-profile-from-c

## Current state
- `config/model-policy.yaml` (schema `version: 1`) defines two profiles:
  `cheap` (`model: claude-haiku-4-5`, `model_env: CLAUDE_CHEAP_MODEL`) and
  `balanced` (`model: claude-sonnet-5-5`, `model_env: CLAUDE_BALANCED_MODEL`).
  It defines three tasks, all on `balanced`: `service_agent`, `mentor_digest`,
  `review_findings_normalize`. The comment there records why the last two left
  `cheap` on 2026-10-01. Today `cheap` is defined but no task routes to it.
- `config/model_policy.py`: `ModelPolicy.resolve()` applies this precedence:
  task-specific legacy env (for example `MENTOR_MODEL`, `SHEPHERD_MODEL`,
  `SERVICE_AGENT_MODEL`), then the profile env (`model_env`), then the YAML
  default. `resolve_model()` loads `DEFAULT_POLICY_PATH`, or
  `MODEL_POLICY_PATH` if set. The YAML default is a plain string, so no model
  allow-list exists in code.
- Consumers: `config/settings.py` (`SERVICE_AGENT_SELECTION`,
  `MENTOR_SELECTION`, `SHEPHERD_SELECTION`) and `orchestrator/resolver.py`.
  The resolver calls `resolve_model` with the manifest's
  `modelPolicy.task` from `agents/_manifests/*/agent.yaml`, and
  `_model_policy_version()` pins `v1+<sha256 of model-policy.yaml>` into each
  plan. No fixture pins that hash. A grep for the current file hash found no
  matches, so editing the YAML breaks no golden test. `orchestrator/options.py`
  passes the resolved string as `model=` into `ClaudeAgentOptions`
  (`claude-agent-sdk==0.2.163`, pinned in `pyproject.toml`, which also pins
  the bundled CLI).
- `.env.example` line 31: `CLAUDE_CHEAP_MODEL=claude-haiku-4-5`.
- `tests/test_model_policy.py` exercises only a synthetic in-memory policy
  (`cheap-default`/`balanced-default`). No test asserts what the committed
  YAML resolves to.

### Inventory of `claude-haiku-4-5` references (grep of the clone)
| Location | Class | Action |
| --- | --- | --- |
| `config/model-policy.yaml` `profiles.cheap.model` | active default | migrate |
| `.env.example:31` `CLAUDE_CHEAP_MODEL` | active default | migrate |
| `CHANGELOG.md:1196-1197` | historical changelog | preserve |
| `docs/benchmarks/capability-discovery.md:71` (CLI side calls in a past run) | historical benchmark | preserve |
| `tests/fixtures/model-usage-records.json` (`claude-haiku-4-5-20251001`) | recorded usage fixture | preserve |
| `tests/test_usage_ledger.py:36` `HAIKU = "claude-haiku-4-5-20251001"` | opaque model key for ledger tests | preserve |
| `tests/*` `model_key: "haiku"` (usage collector tests) | opaque key, not a model default | preserve |
| `docs/adr/012-...md:41,43,220-221` (`mentor_digest`/`review_findings_normalize` -> `cheap`) | stale routing description (no model id) | add a dated note; do not change routing |

## Proposed solution
1. **Default change**: in `config/model-policy.yaml` set
   `profiles.cheap.model: claude-haiku-5-5`. Add a one-line comment giving the
   migration date, issue #600, and the rollback (`CLAUDE_CHEAP_MODEL`). Leave
   the `balanced` profile and the `tasks:` mapping byte-identical.
2. **`.env.example`**: set `CLAUDE_CHEAP_MODEL=claude-haiku-5-5`. Add a comment
   saying `claude-haiku-4-5` is the rollback value. The rest of the file's
   comments are in Russian; the new comment is in English, per this proposal's
   output-language rule.
3. **Committed-policy tests** (`tests/test_model_policy.py`, new section that
   loads `ModelPolicy.load(DEFAULT_POLICY_PATH)` with `CLAUDE_CHEAP_MODEL`,
   `CLAUDE_BALANCED_MODEL`, `MENTOR_MODEL`, `SHEPHERD_MODEL` and
   `SERVICE_AGENT_MODEL` cleared through `monkeypatch.delenv`):
   - the `cheap` profile default resolves to `claude-haiku-5-5` with
     `source == "policy"`. `ModelPolicy` exposes no public profile lookup, so
     the test either resolves a task injected into a copy of the loaded
     document, or reads `yaml.safe_load` of the committed file and builds
     `ModelPolicy` from it with an extra probe task `_probe_cheap: cheap`.
     This proposal uses the second option, which avoids widening the
     `ModelPolicy` API;
   - with `CLAUDE_CHEAP_MODEL=claude-haiku-4-5`, it resolves to
     `claude-haiku-4-5`, `source == "CLAUDE_CHEAP_MODEL"` (rollback);
   - a routing-boundary guard: `service_agent`, `mentor_digest` and
     `review_findings_normalize` resolve to profile `balanced`, model
     `claude-sonnet-5-5`. The test also asserts that no committed task maps
     to `cheap`. If a future change moves a judgement task onto `cheap`, this
     test fails and forces the change to be deliberate, with its own
     evaluation.
4. **Opt-in provider smoke test**: add
   `tests/test_model_smoke_live.py`, marked `@pytest.mark.live` and skipped
   unless `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` is set and
   `MCTL_LIVE_MODEL_SMOKE=1`. The test resolves the cheap model from the
   committed policy, builds options through the same `ClaudeAgentOptions`
   construction used in `orchestrator/options.py` (no tools, `max_turns=1`,
   a small budget), and runs one `query()`. It asserts a non-error
   `ResultMessage` whose `model_usage` key starts with `claude-haiku-5-5`. It
   then repeats the run with `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` to prove
   rollback end to end. If the repo has no `live` marker yet, register it in
   `pyproject.toml` under `[tool.pytest.ini_options]` so the default run
   excludes it. The PR body records the smoke result (model keys, pass/fail).
5. **Bounded quality check**: add `tools/cheap_tier_eval.py` and
   `docs/benchmarks/haiku-5-5-cheap-tier.md`.
   - The workloads are a fixed, checked-in set of about 10 cases per task
     under `tests/fixtures/cheap_tier_eval/`. They cover tasks suited to the
     cheap tier: (a) summarize a CI log excerpt into a fixed JSON schema;
     (b) classify an issue title/body into a closed label set; (c) extract
     `{file, line, severity}` tuples from a formatted review comment whose
     severity token is explicit. Each case has an expected answer, so scoring
     is a deterministic comparison, with no LLM judge.
   - For each model (`claude-haiku-4-5`, `claude-haiku-5-5`) the script
     records success/correctness, wall and API latency (`duration_api_ms`),
     input/output/cache tokens from `ResultMessage.model_usage`, the
     SDK-reported `costUSD`, and the rate of invalid or unparsable JSON
     outputs. Cost is taken from the SDK rather than a local price table,
     consistent with `tools/capability_bench.py`, which deliberately computes
     no USD.
   - The note states its sample size and that it is not evidence for routing
     judgement-sensitive tasks to `cheap`.
6. **Docs**: add a dated note to `docs/adr/012-...md` near the routing table
   saying that `mentor_digest`/`review_findings_normalize` moved to `balanced`
   on 2026-10-01 and that `cheap` now defaults to Haiku 5.5 (#600). Historical
   rows stay as written.

## Alternatives
- **Add a new `cheap_v2`/`haiku55` profile and leave `cheap` on 4.5.** This
  would let tasks opt in one by one, but no task uses `cheap` today. It adds
  schema surface the issue rules out ("Reworking the model-policy schema")
  and leaves a stale default behind. Dropped.
- **Only change `.env.example` and the deployment env (`CLAUDE_CHEAP_MODEL`)
  and leave the YAML on 4.5.** The repo default and the deployed value would
  then disagree, the committed plan pin (`model_policy_version`) would not
  reflect the actual model, and the issue explicitly asks for the YAML
  change. Dropped.
- **Pin the dated snapshot id instead of the alias.** This is more
  reproducible, but it diverges from the issue and from the existing
  alias-style `balanced` entry. It is recorded as an open question and is a
  one-line follow-up if reviewers want it.
- **Rewrite all `claude-haiku-4-5` strings, including fixtures.** This would
  falsify historical usage records and break the `model_key` semantics the
  ledger tests depend on. Dropped, per the issue.

## Platform impact
- **Runtime behaviour**: no committed task routes to `cheap`, so production
  runs resolve the same models as before. The plan-pinned
  `model_policy_version` hash changes, because the YAML content changes.
  This is expected and matches how routing edits have been audited before.
  Any deployment that sets `CLAUDE_CHEAP_MODEL` explicitly (for example in
  mctl-gitops CWFT env or Vault) keeps its value until that is changed
  separately. The PR should check mctl-gitops for such a setting and note it.
- **Backward compatibility**: env precedence is unchanged.
  `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` restores the old model with no code
  change.
- **SDK/provider risk**: the pinned bundled CLI (`claude-agent-sdk==0.2.163`)
  might reject or mis-map an id newer than its release. The live smoke test
  is there to detect this. If it fails, bumping the SDK is a separate,
  explicitly reviewed change, and the default change waits for it.
- **Cost**: the default suite is unaffected. The evaluation and smoke test
  are a one-off of roughly 60 short calls (about $1 or less), run manually.
- **Safety boundary**: the new committed-policy guard test makes the
  judgement-routing boundary a CI invariant instead of only a YAML comment.
