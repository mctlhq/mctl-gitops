# Risk register

Not ROADMAP. Scored for Type I design as of 2026-08-17, tags and
R12 date checked 2026-09-04. Owner is the
founder unless noted. Review at least quarterly with the access review.

Scale: High / Medium / Low for inherent and residual.

| ID | Risk | TSC | Inherent | Treatment | Residual | Status |
|---|---|---|---|---|---|---|
| R1 | GitHub org without required MFA | CC6 | High | Enable org 2FA requirement; evidence in `evidence/github-org-mfa.md` | Low | Closed 2026-08-19 — requirement `true`; `2fa_disabled` count 0 |
| R2 | Single control-plane node loss | A1 | High | etcd S3 + restore runbook; second CP is Horizon 2 (F11) | Medium | Accepted |
| R3 | Vault east-west plaintext | C1 | Medium | Edge TLS + NetworkPolicy; TLS-from-day-one on future prod cluster (F15) | Medium | Accepted |
| R4 | First packet to Vault rejected (NP race) | A1/CC7 | Medium | Wait loop on `vault-backup` only (gitops#862). Do not spray | Low on that Job | Accepted; 17 Aug 03:00:40Z succeeded |
| R5 | Apiserver audit stays on CP disk | CC7 | Medium | AuditPolicy + rotation; Loki scrape is hours of infra | Medium | Accepted for Type I |
| R6 | Alert/Job GC hides failures | CC7 | Medium | VaultBackupStale on CronJob timestamps | Low for Vault backup | Partial — other Jobs still GC |
| R7 | Admin GitHub ruleset bypass | CC1/CC5 | High | Documented exception + emergency-change.md + quarterly review | Medium | Compensating — gitops admin bypass closed; still on api / agent / agents / web |
| R8 | Bot writes `image.tag` to main | CC8 | Low | Scoped workflows; least-privilege token (`CLAUDE.md`) | Low | Accepted exception |
| R9 | Open OAuth DCR | CC6 | Medium | Allowlist + rate limit + TTL; token would break MCP onboarding | Medium | Product choice |
| R10 | No vendor SOC reports | CC9 | Medium | `vendors.md` inventory; collect Hetzner/CF/GitHub annually | Medium | Open paper |
| R11 | Incident pipeline suspended | CC7 | High | Unsuspend; last tick 2026-08-17T06:15Z `suspend=false` | Low | Closed as designed |
| R12 | PSS still baseline | CC6 | Low | audit/warn restricted; step 2 after 29.08 not done (F18) | Low | Accepted Horizon 3 — re-checked 2026-09-04, still `enforce=baseline` |
| R13 | Fraud / payment abuse | CC3 | Low | No platform payments; see fraud-memo.md | Low | Accepted |

Do not add DCR-token, docs CSP, or a second CP as "Type I blockers". They are
product or Horizon 2/3.
