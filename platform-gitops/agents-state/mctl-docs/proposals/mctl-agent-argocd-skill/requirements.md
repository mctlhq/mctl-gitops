# mctl-agent-argocd-skill: Document argocd_sync_failed diagnostic skill

## Context
Commit `74ee766` in mctl-agent (2026-05-06) added a new built-in skill:
`argocd_sync_failed`. It was merged in response to a real incident: the
`external-secrets` ArgoCD application was stuck `Degraded` for 6 days
(2026-05-01 → 2026-05-07) while the agent system never proposed any recovery —
`ArgoCDDriftSkill` only handles benign `OutOfSync+Healthy` drift, so
`OutOfSync+Degraded` apps had no diagnostic path.

The new skill:
- **Triggers on:** `OutOfSync+Degraded` (priority 60), `Degraded` (priority 55),
  and escalates to priority 80 + HIGH confidence when the status message contains
  a known recovery-drill signature.
- **Recognises two failure patterns:**
  1. CRD storedVersion conflict — status contains "must remain in spec.versions" or
     "missing from spec.versions". Recovery: kubectl patch to remove the stale
     storedVersion.
  2. managedFields poisoning — status contains "request to convert CR from an
     invalid group/version". Recovery: kubectl commands to strip managedFields.
- **Diagnose() returns** the exact recovery commands as plain text.
- **Fix() is nil** — the skill never applies changes autonomously; the diagnosis
  lands in a Telegram message for human approval.
- **AlertManager wiring:** the new `ArgoCDApplicationDegraded` and
  `ArgoCDApplicationSyncFailed` alerts (mctl-gitops PR #142) now map to
  `TypeArgoCDDegraded` in the alert classifier, so the skill is triggered
  automatically on alert reception.

The skill is in production as of mctl-agent 1.10.1 (mctl-gitops `286af74`,
2026-05-07). `docs/platform/components.md` covers mctl-agent but does not
document this skill or the human-approval pattern it follows.

## User stories
- AS a **platform admin** I WANT to know that mctl-agent will automatically diagnose
  stuck-degraded ArgoCD applications SO THAT I understand I will receive actionable
  Telegram messages when ArgoCD apps fail, without needing to file a ticket or
  investigate manually.
- AS a **platform admin** I WANT to know which failure patterns the agent recognises
  SO THAT I understand what the diagnosis covers and what it does not (i.e., I am not
  surprised when the agent does not diagnose a novel failure type).
- AS a **developer** onboarding to the platform I WANT the components page to list
  all active mctl-agent skills SO THAT I have a complete picture of the self-healing
  capabilities.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/components.md` and navigates to the mctl-agent
  section THE SYSTEM SHALL list `argocd_sync_failed` as an active built-in skill.
- WHEN a reader consults the skill entry THE SYSTEM SHALL describe the two trigger
  conditions (`OutOfSync+Degraded`, `Degraded`) and that AlertManager alerts also
  trigger the skill.
- WHEN a reader wants to know what the skill does THE SYSTEM SHALL explain that it
  diagnoses the failure and posts recovery commands to Telegram for human approval
  (Fix() is nil — no autonomous cluster changes).
- WHEN a reader wants to know which patterns are recognised THE SYSTEM SHALL list
  the two known recovery-drill signatures: CRD storedVersion conflict and managedFields
  poisoning.
- IF a reader wonders whether the agent will auto-apply the fix THE SYSTEM SHALL
  state explicitly that the skill does NOT apply changes autonomously — a human must
  approve and execute the recovery commands.

## Out of scope
- Documenting the Go implementation details of `argocd_sync_failed.go`.
- Providing runbook steps for CRD storedVersion conflicts (that belongs in
  `docs/reference/troubleshooting.md`; cross-link from this page).
- Documenting the AlertManager alert configuration (covered by the mctl-gitops repo).
- Documenting the priority scoring system internal to mctl-agent.
