# Compensating controls — solo operator

COSO expects segregation of duties. This platform is solo-founded
(`ROADMAP.md`) with Claude agents. A CPA will sample that. These
compensations are the design, not a claim that SoD exists.

## Facts

- One human owner: `@mashkovd`.
- GitHub rulesets still include `bypass_actors` for repository admin on
  api / agent / agents / web. gitops `main-protection` does not
  (`current_user_can_bypass=never` as of 2026-09-03). There is no
  documented emergency policy except `emergency-change.md` in this
  directory.
- `gitops-bump.yaml` / `release-deploy.yaml` commit `image.tag` directly
  to `main` (allowed exception in `CLAUDE.md` / workspace `AGENTS.md`).
- CODEOWNERS (`* @MashkovD`) on api / gitops / agent; academy /
  telegram / openclaw already had it.

## Compensations

1. **Every human change still goes through a PR** unless it is the
   documented bot tag bump or an emergency recorded under
   `emergency-change.md`.
2. **Claude review** must have no unaddressed P1/P2 on non-trivial PRs.
   That is a second reader, not a second human.
3. **Argo CD** is the cluster write path. kubectl as admin is break-glass
   and must be logged in the emergency file.
4. **Quarterly self-review** (see `access-review.md`): org members, Vault
   policies, Argo `policy.csv`, Backstage admins, this bypass list.
5. **Bots cannot widen their own token.** Token and workflow changes are
   human PRs.

## Residual

The same person can bypass the ruleset, merge, and sync. Type I can
include that if the system description says so. Type II will want a
second human or a tighter bypass (time-limited, logged).
