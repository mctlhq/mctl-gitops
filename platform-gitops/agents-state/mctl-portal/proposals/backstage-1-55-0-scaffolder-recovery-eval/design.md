# Design: backstage-1-55-0-scaffolder-recovery-eval

## Current state
mctl-portal runs Backstage with a custom `scaffolder` plugin used for
tenant/service onboarding, which commits generated manifests to
`mctl-gitops` and triggers Argo Workflow templates for provisioning (see
`context/architecture.md`). Production is currently pinned at Backstage
revision 2.6.3 (per `context/current-version.md` and the ArgoCD status in
tenant `admins`). Today, a stuck or failed scaffolder task has no
documented recovery mechanism — an operator must manually inspect Argo
Workflow state and, in the worst case, re-run onboarding from scratch.
ADR 0001 and `context/architecture.md` both require waiting roughly a week
after a Backstage release before adopting it, to let community-plugins
compatibility catch up; the already-completed
`backstage-1-54-7-oauth-normalization` proposal covered a different, prior
patch release and is not affected by this evaluation.

## Proposed solution
Run a staged, non-production evaluation of Backstage v1.55.0:
1. **Timing gate**: do not begin any hands-on evaluation work until at
   least one week has elapsed since the v1.55.0 release, per ADR 0001.
2. **Elasticsearch 8 applicability check**: confirm from `search` plugin
   configuration in `packages/backend` whether mctl-portal's search
   backend depends on Elasticsearch at all; `context/architecture.md`
   lists no such dependency today, so the expected outcome is "not
   applicable," but this must be confirmed against the actual v1.55.0
   release notes/migration guide rather than assumed.
2b. If the ES8 requirement turns out to be forced regardless of search
    backend choice, treat that as a hard blocker (see acceptance criteria)
    and stop the evaluation there.
3. **Custom plugin compatibility matrix**: in a lower (non-production)
   environment, build and smoke-test each custom/community plugin against
   v1.55.0: `kubernetes`, `observability`, `scaffolder`, `techdocs`. Record
   pass/fail per plugin.
4. **Catalog API breaking-change review**: enumerate the deprecated catalog
   APIs marked breaking in v1.55.0 and check mctl-portal's own code and
   custom plugins for usage of any of them.
5. **Scaffolder task recovery spike**: specifically exercise the new task
   recovery capability against a deliberately-interrupted scaffolder task
   in the lower environment, to validate it actually resolves the
   "no recovery story" gap before recommending adoption.
6. **Decision output**: produce a short findings write-up (pass/fail per
   check above) and, only if everything passes, open a *separate* follow-on
   proposal to actually bump production. This proposal's own scope ends at
   the evaluation and findings.

## Alternatives
- **Adopt v1.55.0 directly in production now**: rejected — violates ADR
  0001's wait-a-week guardrail and risks an Elasticsearch 8 forced
  dependency and catalog-API breaking changes hitting production before
  compatibility is verified.
- **Ignore v1.55.0 entirely until the next major**: rejected — scaffolder
  task recovery addresses a real, currently-undocumented operational gap
  (stuck onboarding tasks); deferring indefinitely delays a genuine
  improvement without justification.
- **Build a custom task-recovery mechanism instead of waiting for upstream**:
  rejected — duplicates upstream effort and diverges mctl-portal further
  from stock Backstage, increasing future upgrade cost; evaluating the
  upstream feature first is cheaper.

## Platform impact
- **Migrations**: none in this proposal's scope — no production deployment
  occurs; any migration work belongs to the follow-on adoption proposal if
  the evaluation passes.
- **Backward compatibility**: production stays on 2.6.3 for the duration
  of this evaluation; no compatibility risk introduced by the evaluation
  itself.
- **Resource impact**: evaluation work happens in a lower environment only;
  no `labs`-tenant impact (mctl-portal runs only in `admins`, and this
  evaluation touches neither `labs` capacity nor shared cluster resources).
- **Risks and mitigations**:
  - Risk: evaluation reveals a forced Elasticsearch 8 dependency that is
    expensive to satisfy. Mitigation: this is exactly what the timing gate
    and ES8-applicability check are designed to surface before any
    production commitment is made.
  - Risk: evaluation is skipped or rushed under pressure to get scaffolder
    recovery quickly. Mitigation: acceptance criteria explicitly block
    production adoption on all compatibility checks passing.
