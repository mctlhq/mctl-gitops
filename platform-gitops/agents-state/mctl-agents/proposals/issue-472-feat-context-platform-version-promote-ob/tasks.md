# Tasks: issue-472-feat-context-platform-version-promote-ob

> **Correction 2026-09-27.** This proposal was split into three slices.
> **This `tasks.md` is Slice A only**: approving this DevLoop runs the
> implementer over every task below, so the file contains exactly the work
> one approval authorizes. The implementation PR says
> `Refs mctlhq/mctl-agents#472` and must not close it.
>
> - **Slice B** — rollout ladder, the behaviour-neutral `observe` shadow pass,
>   release telemetry: mctlhq/mctl-agents#527 (does not depend on #526).
> - **Slice C** — production evidence validation, soak gate, production
>   promotion, runbook: mctlhq/mctl-agents#528 (hard-depends on
>   mctlhq/mctl-agents#526).
>
> Their task text moved verbatim into those issues. Task numbers are kept, so
> task 11 and T13 still read as before.

## Slice A — inert contract, catalog and validation

- [ ] 1. Write `docs/adr/019-context-strategy-release-contract.md` (019 is the
      next free number in `docs/adr/`; 016 is occupied by the shepherd merge-approval ADR and 017/018 are also taken). It fixes: the `ContextStrategyVersion` and
      `ContextStrategyBinding` shapes; the `implementationHash` encoding; the
      reuse of ADR 007's `published`/`deprecated`/`disabled` version lifecycle
      and its `publish`/`promote`/`deprecate`/`disable`/`rollback` transition
      table; the `off/observe/enforce/only` ladder; the `evidence` seam to
      mctlhq/mctl-agents#526 (the undelivered evaluator half of #266); the
      source-of-truth boundary (git owns desired
      catalog state, the snapshot and the execution record own what ran); and a
      restatement of ADR 009 sec. 5 ("context relevance is never an
      authorization mechanism") as normative for everything below.
      — DoD: ADR merged with `Status: proposed`, cross-linked from ADR 009's
      follow-up table and from ADR 015's non-goal line, and it states which of
      its own decisions a follow-up may not reopen, in ADR 007/009's style.

- [ ] 2. Add ADR 009 **amendment 2** to
      `docs/adr/009-context-snapshot-contract.md` and implement it in
      `orchestrator/context_snapshot.py`: `ContextStrategy` (`:649-678`) gains
      optional `release_revision: int | None` and `content_hash: str | None`.
      `to_dict()` omits each when unset; they enter the snapshot's
      `content_hash` only when present; `from_dict` accepts them and still
      rejects every unknown key; `content_hash`, when set, is validated by the
      existing `_require_sha256`. Follow amendment 1's `conflicts` precedent
      byte-for-byte (`:866-867`, `:1202-1206`).
      — DoD: `tests/fixtures/context/investigator-snapshot.json` and its
      asserted hash are **unchanged**, and a new test proves a snapshot sealed
      without the two fields has a `snapshot_id` identical to one sealed before
      this change.

- [ ] 3. Create the catalog: `config/context-strategies/versions/
      deterministic-fixed-order/1.0.0.yaml`,
      `config/context-strategies/versions/trust-freshness-ranked/1.0.0.yaml`,
      and a **shadow-only** binding at
      `config/context-strategies/bindings/shadow/issue-investigator.yaml`
      whose revision 1 pins `deterministic-fixed-order 1.0.0` — today's
      default, made explicit, with `evidence: {kind: none}` and a reason
      recording that revision 1 is the inert baseline. Do **not** create a
      production binding in Slice A. (depends on 1)
      — DoD: the shadow binding resolves to exactly the strategy the
      investigator runs today; no behaviour changes because nothing reads it
      yet; there is no production promotion that could be mistaken for having
      passed an evidence gate.

- [ ] 4. Add `tools/context_release.py` with `publish`, `promote`, `rollback`
      and `resolve` subcommands, modelled on `tools/publish_agent_release.py`
      (argparse, `--dry-run`, non-2xx/failure returned as a value not an
      exception, per-target isolation so one bad document never half-writes the
      catalog). `publish` computes `contentHash` over the version document
      minus that field, and `implementationHash` over the declared files in
      sorted path order as length-prefixed `"<len>\n<path><len>\n<bytes>"`
      pairs — the exact encoding, and the exact ambiguity rationale,
      `publish_agent_release.prompt_hash` already documents. (depends on 3)
      — DoD: `publish` regenerates task 3's two version documents byte-for-byte
      from the committed code; `promote` and `rollback` refuse to mutate or
      drop any existing revision.

- [ ] 5. Add `orchestrator/context_release.py`: the frozen
      `ContextStrategyVersion` / `ContextStrategyBinding` /
      `ResolvedContextStrategy` types, `load_version`, `load_binding`,
      `resolve(agent, environment)`, and the pure `promote()` / `rollback()`
      document builders. Reading and hashing follow
      `resolver._read_yaml_and_hash` — parse and hash the same bytes. Every
      check is a raise naming the file and the fix, in
      `resolver.load_release_binding`'s style (`resolver.py:768-862`):
      apiVersion/kind allow-list, path-vs-`metadata.{agent,environment}`
      cross-check, positive-integer strictly-increasing gapless revisions,
      non-`disabled` lifecycle, and recomputation of both hashes against the
      files in the running image. In Slice A a `production` promotion is
      **always refused** with the closed-vocabulary code `evidence-missing`:
      the evidence it would validate is #526's record, whose format does not
      exist yet, so Slice A does not guess at it. The real checks
      (`context-eval`, exact identity, <= 7 days, >= 3 consecutive observe
      runs, no `hash-mismatch`) are mctlhq/mctl-agents#528. Verdicts are a closed
      vocabulary, in `orchestrator/lifecycle/contract.py`'s style: anything
      outside it is `unknown`, never silently `ok`. (depends on 3)
      — DoD: unit tests cover every refusal path; a hash mismatch raises with
      the exact `tools/context_release.py publish` command in the message.

- [ ] 11. CI drift guard: a pytest test (not a new workflow —
      `.github/workflows/pr-validation.yml` already runs pytest, ruff and mypy)
      that recomputes every published version's `implementationHash` against
      the working tree and fails with the exact republish command when they
      disagree, plus a `tools/context_release.py resolve` preflight asserting
      every committed binding resolves on this commit. (depends on 5)
      — DoD: deliberately editing `rank_candidates` without republishing fails
      CI with an actionable message.

## Slice B and Slice C

Not in this proposal's implementation run: see mctlhq/mctl-agents#527 (tasks
6-10, tests T7-T10 and T12) and mctlhq/mctl-agents#528 (tasks 12-13, the
production half of T5).

## Tests

- [ ] T1. Golden-fixture stability: `tests/fixtures/context/
      investigator-snapshot.json` and its asserted `content_hash`/`snapshot_id`
      are unchanged by task 2. This is the single most important test in the
      proposal — if it fails, every persisted snapshot's identity moved.
- [ ] T2. Optional-field semantics: sealing with `release_revision`/
      `content_hash` unset produces byte-identical canonical JSON to sealing
      before the change; setting them changes `content_hash`; `from_dict`
      round-trips both cases and still rejects an unknown key inside
      `strategy`.
- [ ] T3. Version loading: unknown `apiVersion`, unknown `kind`, `disabled`
      lifecycle, absent implementation file, and a tampered
      `implementationHash` each raise with a message naming the file.
- [ ] T4. Binding loading: `metadata.agent`/`metadata.environment` disagreeing
      with the path, a non-positive revision, a duplicated revision, a gap in
      the revision sequence, and an empty history each raise.
- [ ] T5. Promotion rules: a `production` promotion is refused with
      `evidence-missing` whatever its `evidence` block says (including a
      well-formed-looking `context-eval` block); the same promotion to `shadow`
      with `evidence.kind: none` and a `reason` is accepted; promoting a
      `deprecated` version is refused while an existing binding on it still
      resolves.
- [ ] T6. Rollback rules: `rollback(to_revision=1)` appends a revision
      restoring revision 1's exact strategy/version/hash triple with
      `rollbackOf: 1`, leaves revisions 1..N intact, and never infers a target;
      rolling back to a revision whose version is now `disabled` is refused and
      names it.

- [ ] T11. Authorization boundary: the recursive field-name assertion (no
      `allow`/`deny`/`permit`/`grant`/`authorized` token) and the subprocess
      import-direction assertion from `tests/test_context_snapshot.py` are
      extended to `orchestrator/context_release.py`, proving no policy path
      imports it.

- [ ] T13. Drift guard: a synthetic edit to a declared implementation file
      makes task 11's test fail with the republish command in its message.
- [ ] T14. End-to-end: `tools/context_release.py publish` then `promote` then
      `resolve` on a temporary catalog root yields the expected
      `ResolvedContextStrategy`, and `--dry-run` writes nothing.

## Rollback

For Slice A alone nothing reads the catalog at runtime, so rollback is a plain
revert of the Slice A PR (tier 4 below, without the `release_revision` caveat,
since no snapshot is sealed under a binding yet). Tiers 1-3 describe the
lifecycle once #527 and #528 land.

Four tiers, fastest first. Each is independently sufficient.

1. **Instant, no deploy, no commit:** unset `CONTEXT_RELEASE_ROLLOUT_MODE` (or
   set it to `off`). The mode is read fresh per run — the same property
   `_context_mode`/`_resolver_mode`/`_capability_mode` already rely on so "an
   operator can roll back by unsetting the env var without a redeploy"
   (`run_issue_investigator.py:149-153`). `AssemblyConfig.from_env()` decides
   again, no catalog file is read, `context_release` is not even imported, and
   snapshots return to the exact bytes they have today.
2. **Keep the ladder, restore fail-open:** set `CONTEXT_RELEASE_REQUIRED=false`
   if an unresolvable binding is blocking runs during an incident. Assembly
   falls back to `deterministic-fixed-order` and continues.
3. **Audited catalog rollback:** `tools/context_release.py rollback --agent
   issue-investigator --environment production --to-revision N --reason ...`,
   merged as a PR. Appends a new revision restoring revision N's exact triple
   with `rollbackOf: N` — history is never rewritten, so what was live at any
   past moment stays answerable.
4. **Full revert:** revert the feature commits. Because every new file is
   additive and the default is `off`, reverting restores prior behaviour
   exactly — with one caveat that must be checked before reverting task 2:
   `ContextSnapshot.from_dict` rejects unknown keys, so a reverted reader will
   refuse a snapshot that was persisted **with** `strategy.release_revision`
   set. Order the revert accordingly — move the ladder to `off` first, let
   in-flight executions drain, and only then revert the schema change; or leave
   task 2 in place, since it is inert while the ladder is `off`.

The blast radius at every tier is bounded by the outer gate: with
`ISSUE_INVESTIGATOR_CONTEXT_MODE=off` — still the shipped default — no
assembly runs at all, so none of this code executes.
