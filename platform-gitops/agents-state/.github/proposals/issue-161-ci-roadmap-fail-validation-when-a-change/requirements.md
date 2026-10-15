# Roadmap CI guard: refuse new required work on a completed epic

## Context
Issue mctlhq/.github#161 asks for a diff-aware CI check. The check must fail a roadmap change that adds required work to an epic whose `spec.lifecycle` is `completed` and leaves that lifecycle `completed`. The trigger was #152, which added a required `trajectory-economics` item to `roadmap/epics/agent-finops.yaml`. That epic was marked `completed` by #155 while #152 was still open. The merge was textually clean and every existing check passed. The result would have been a manifest that says `completed` while it holds an open, unbound required item.

Today nothing in `roadmap/scripts/` reads `lifecycle` except `publish.py`, which only copies it into the publication. `.github/workflows/roadmap-validate.yml` checks out the PR with the default shallow history and runs `validate.py roadmap/epics` on the final tree only. A validator that reads only the final tree cannot tell "added after completion" from "always there". So the check has to compare the change against its base, and it has to fail closed when the base cannot be read.

## User stories
- AS a roadmap reviewer I WANT CI to fail when a change adds required work to a completed epic SO THAT a manifest never claims `completed` while holding unfinished required work.
- AS a roadmap author I WANT a documented, reviewable way to extend completed work (add the item as optional, or reopen the epic to `active`/`paused` in the same change) SO THAT the guard does not block legitimate follow-up work.
- AS a platform operator I WANT an unreadable or missing base to fail the check with a distinct message SO THAT "could not observe" is never reported as "nothing changed".

## Acceptance criteria (EARS)
- WHEN an epic's head lifecycle is `completed` and its set of `required: true` work-item ids contains any id that is not in the base epic's required set THE SYSTEM SHALL report a `RequiredItemAdded` violation naming the epic and each new id, and exit 1.
- WHEN an epic's head lifecycle is `completed` and a work item that exists in base with `required: false` has `required: true` in head THE SYSTEM SHALL report a `RequiredFlagRaised` violation and exit 1.
- WHEN a manifest is new in head (its `metadata.name` exists in no base manifest, and no base manifest exists at the same path), its lifecycle is `completed`, and it holds a `required: true` item without an `issue` binding THE SYSTEM SHALL report a `BornCompletedUnbound` violation and exit 1.
- WHEN an epic's base lifecycle is `completed` and its head lifecycle is `active` or `paused` THE SYSTEM SHALL NOT report a violation for that epic, whatever required items the change adds.
- WHEN an epic's head lifecycle is anything other than `completed` THE SYSTEM SHALL NOT report a violation for that epic.
- WHEN a manifest exists in base and is deleted in head THE SYSTEM SHALL NOT report a violation for it.
- WHEN a change removes required items from, or lowers `required` to `false` on, a completed epic THE SYSTEM SHALL NOT report a violation (required work did not grow).
- IF the base ref cannot be resolved to a commit (for example a missing merge base, or a shallow checkout without that commit) THEN THE SYSTEM SHALL exit 2 with a message that starts `base-unresolvable:`.
- IF the base tree cannot be listed or a base manifest blob cannot be read THEN THE SYSTEM SHALL exit 2 with a message that starts `base-unreadable:` and names the path.
- IF a base manifest is not valid YAML, its root is not a mapping, or it lacks `metadata.name`, `spec.lifecycle` or a `spec.workItems` list whose entries carry `id` and a boolean `required` THEN THE SYSTEM SHALL exit 2 with a message that starts `base-malformed:` and names the path.
- IF a head manifest fails `validate.validate_document` THEN THE SYSTEM SHALL exit 2 with a message that starts `head-invalid:`. The guard never judges a head that the validator rejects.
- WHEN the workflow runs on `pull_request` THE SYSTEM SHALL fetch full history, compute `git merge-base` of the PR base SHA and the PR head SHA, fail the job if that lookup fails, and run the guard between that commit and the checked-out tree.
- WHEN the workflow runs on `push` to `main` with a non-zero `github.event.before` THE SYSTEM SHALL run the guard between that commit and the pushed tree.
- IF the workflow runs on `push` with an all-zero `github.event.before` THEN THE SYSTEM SHALL emit an explicit `::warning::` "no base" annotation and skip only the guard step. It SHALL NOT report the guard as passed.
- WHILE the guard is part of `roadmap-validate.yml` THE SYSTEM SHALL keep `permissions: {}` and perform no network or GitHub API calls in the guard.
- WHEN `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` runs THE SYSTEM SHALL pass, including new tests for every rule and error above.

## Out of scope
- A state-based check that flags an epic whose manifest says `completed` while `completion.py` computes `incomplete` (for example, a required issue reopened on GitHub). The implementer may file it as a separate issue.
- Verifying offline that a bound required item's GitHub issue is closed. The guard has no token and no snapshot in CI. See Open questions.
- Changing `validate.py`, `completion.py`, `health.py` or the EpicDefinition schema.
- Guarding the `proposed` and `archived` lifecycles, or the transition into `completed`.

## Open questions
- "Born `completed` with a required item that is not bound and closed": the guard is offline, so it can see whether an item is bound but not whether its issue is closed. Chosen interpretation: fail on unbound required items, and print an informational line (not a pass claim) listing bound required items whose closure the guard did not verify. Closure verification belongs to the out-of-scope state-based check. A reviewer may want stricter behaviour, such as requiring a snapshot.
- Epic identity across base and head: matching uses `metadata.name` first, then the same file path. A change that renames `metadata.name` and moves the file at the same time is treated as a new manifest, so the born-completed rule applies to it.
- The issue's acceptance asks to show the guard "red again on that mutation when the guard step is removed from the workflow". With the step removed, CI cannot go red from the guard. Chosen interpretation (see tasks.md): three evidence runs. (1) Green on the converged tree. (2) Red on the #152 mutation with the guard present. (3) The same mutation with the guard step removed, which goes green and so proves the guard is the only thing that catches it. In addition, a unit test reverts the guard logic (a no-op checker) and asserts that the mutation test fails. The reviewer should confirm this reading.
- The issue cites AGENTS.md rules ("could not observe" is never "observed absent", proving a check both ways). The AGENTS.md in this clone contains only the active-plans section. The same principle is stated in `roadmap/README.md` and in the `completion.py` docstring, and the proposal follows it.
