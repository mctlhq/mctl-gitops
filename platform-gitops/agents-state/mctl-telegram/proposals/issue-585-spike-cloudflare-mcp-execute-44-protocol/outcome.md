# Outcome — issue-585 spike (Cloudflare MCP protocol/OAuth gate)

`.status.yaml` records what the DevLoop run produced: `status: implemented`,
`pr: https://github.com/mctlhq/mctl-telegram/pull/603`. That is accurate as a
log of the automation and is deliberately left alone.

It is **not** the accepted artifact. This file exists so nobody — human or
machine — reads the `pr:` field a month from now and concludes that #603 is the
implementation of record.

## Accepted artifact

| | |
|---|---|
| Merged PR | [mctlhq/mctl-telegram#604](https://github.com/mctlhq/mctl-telegram/pull/604) |
| Merge commit | `2afa713` on `main`, 2026-09-10T00:43:14Z |
| Superseded | [#603](https://github.com/mctlhq/mctl-telegram/pull/603) — the DevLoop-authored PR, closed unmerged |
| Compatibility matrix | [mctlhq/.github#44](https://github.com/mctlhq/.github/issues/44#issuecomment-5610360695) |
| Follow-up P3s | [mctlhq/mctl-telegram#605](https://github.com/mctlhq/mctl-telegram/issues/605) |

## Why two implementations existed

The first DevLoop attempt failed `no-commits`: the agent image carried no Go
toolchain, so the implementer could not build and correctly refused to commit
code it had not compiled. The environment was fixed
([mctl-agents#328](https://github.com/mctlhq/mctl-agents/pull/328), image
release 1.40.2) and the run was retriggered, producing #603 — by which point a
hand-written branch already existed. Both were kept deliberately, on the user's
instruction, and compared.

#604 was taken as the base. From #603 it adopted the negative case on a missing
`Mcp-Protocol-Version` header and the fixture built on the real SDK server.
Mutation testing showed the #603 suite missed two cases #604 covers: the
absent-annotation path of the read-only guard, and a credential-carrying field
in the report. Neither implementation was strictly better as a whole, which is
why the comparison was run rather than assumed.

## Scope actually closed

Repository-side Phase A only. The probe and the pre-registered public-client
OAuth path are merged and tested; six modern negatives are enforced and each is
gated on a positive of its own kind, so a rejection is never credited to a
mutation that had no part in it.

Phase B is **not** decided, and the live rows of the matrix are
`PENDING-OPERATOR`: they need a deployed build containing `2afa713`, a bearer
for `tg.mctl.ai/mcp`, and a configured Portal. If Cloudflare turns out to
require confidential-client authentication, Phase B is BLOCKED and gets its own
security-reviewed issue — there is no fallback to a credential-bearing token
endpoint auth method.

> A later agent write to `.status.yaml` may drop its `notes:` line. This file is
> the durable record; the note is the convenience pointer.
