# Tasks: backstage-1-55-0-scaffolder-recovery-eval

- [ ] 1. Confirm at least one week has elapsed since the v1.55.0 release
      date before starting hands-on evaluation work — DoD: elapsed-time
      check documented; evaluation start date recorded.
- [ ] 2. Review v1.55.0 release notes/migration guide for the Elasticsearch
      8 requirement and cross-check against mctl-portal's actual `search`
      plugin configuration (depends on 1) — DoD: written determination of
      "applicable/forced," "conditional," or "not applicable," with
      supporting evidence cited.
- [ ] 3. Enumerate deprecated catalog APIs marked breaking in v1.55.0 and
      grep mctl-portal's backend/app code and custom plugins for usage
      (depends on 1) — DoD: list of any usages found, or explicit
      confirmation of none found.
- [ ] 4. In a lower environment, build and smoke-test each custom plugin
      (kubernetes, observability, scaffolder, techdocs) against v1.55.0
      (depends on 2, 3) — DoD: pass/fail recorded per plugin with build/test
      logs attached.
- [ ] 5. Exercise the scaffolder task-recovery feature against a
      deliberately-interrupted task in the lower environment (depends on 4)
      — DoD: recovery outcome documented (recovered/not recovered, manual
      steps required if any).
- [ ] 6. Compile findings into a decision write-up: ES8 applicability,
      catalog-API impact, per-plugin compatibility, task-recovery efficacy
      (depends on 2, 3, 4, 5) — DoD: write-up committed alongside this
      proposal; explicit go/no-go recommendation stated.
- [ ] 7. IF the findings are all-pass, open a separate follow-on proposal
      for production adoption (depends on 6) — DoD: new proposal slug
      created referencing this evaluation's findings. This task is
      out-of-scope to execute here beyond opening the follow-on proposal.

## Tests
- [ ] T1. Verify search functionality (full-text catalog search) still
      works in the lower environment against v1.55.0 regardless of the
      ES8 finding.
- [ ] T2. Smoke test: kubernetes plugin renders pod/service/CRD views
      correctly against v1.55.0.
- [ ] T3. Smoke test: observability plugin renders Prometheus graphs
      correctly against v1.55.0.
- [ ] T4. Smoke test: scaffolder onboarding flow (template generation +
      mctl-gitops commit + Argo Workflow trigger) completes successfully
      against v1.55.0.
- [ ] T5. Smoke test: techdocs build/publish flow completes successfully
      against v1.55.0.
- [ ] T6. Task-recovery test: an interrupted scaffolder task is recovered
      without requiring a full onboarding restart.

## Rollback
This proposal makes no production changes, so there is no production
rollback needed. If the lower-environment evaluation environment itself
needs to be reset (e.g. corrupted by a failed v1.55.0 build), tear down and
recreate it from the current 2.6.3 baseline. Production in `admins` remains
on 2.6.3 throughout and is never repointed as part of this proposal.
