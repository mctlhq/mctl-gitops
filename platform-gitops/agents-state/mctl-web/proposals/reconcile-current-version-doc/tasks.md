# Tasks: reconcile-current-version-doc

- [ ] 1. Query `mctl_get_service_status` and `mctl_get_service_config` for
      admins/mctl-web and record the raw `imageTag` and any other version-relevant
      fields returned — DoD: raw tool output captured and attached to this task's
      notes/PR description.
- [ ] 2. Cross-reference the returned `imageTag` (7.3.0) against the repo's release
      history (git tags, CI build logs, or release notes) to determine what versioning
      scheme it represents relative to the Nuxt app version (depends on 1) — DoD: a
      clear written explanation of what "7.3.0" is (app release tag, image build tag,
      etc.) and how it relates to the Nuxt framework version.
- [ ] 3. Draft the corrected content for `context/current-version.md`, including the
      verified version, its labeled meaning, and today's date as the "last update of
      this file" (depends on 2) — DoD: draft text ready for whoever executes the
      deploy/update step (this is a hand-off, since `context/` is read-only to
      spec-writer/analyst/researcher agents).
- [ ] 4. Whoever owns the deploy/update process applies the corrected content to
      `context/current-version.md` (depends on 3) — DoD: file committed with the
      corrected version, label, and date.
- [ ] 5. Add or update the ADR convention note so the "update this file on every
      service update" instruction in `context/current-version.md` is reinforced as a
      mandatory step, not optional (depends on 4) — DoD: an ADR or process note exists
      confirming the update-on-deploy requirement.
- [ ] 6. (Optional, recommended) Propose a periodic sanity check — e.g., researcher or
      analyst compares recorded version vs. live `mctl_get_service_status` on a
      regular cadence and flags drift in the inbox if found (depends on 4) — DoD:
      recommendation documented; not required to implement automation as part of this
      proposal.

## Tests
- [ ] T1. Confirm `mctl_get_service_status` and `mctl_get_service_config` both agree
      on the same `imageTag` value before finalizing the correction (consistency
      check).
- [ ] T2. After task 4, re-run `mctl_get_service_status` for admins/mctl-web and
      confirm the value matches what was written into `context/current-version.md`.
- [ ] T3. Manual review: confirm the corrected file clearly states what versioning
      scheme the recorded number represents (no ambiguity for future readers).

## Rollback
If the "verified" version turns out to be wrong or the versioning-scheme
interpretation is later found to be incorrect, this is a low-risk, easily-reversible
documentation change: revert `context/current-version.md` to its prior content (or to
a newly-corrected value) in a follow-up commit. There is no application state,
deployment, or user-facing impact to roll back, since this proposal does not touch
running services.
