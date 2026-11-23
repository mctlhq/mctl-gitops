# Spike report: Cloudflare Kitesurf as a governed browser execution backend for MCTL (research only)

## Context

Issue mctlhq/.github#343 asks for a research-only spike. The question is whether
Cloudflare Kitesurf, an experimental, stateless, Apache-2.0 browser engine that
runs on Cloudflare Workers and speaks CDP, can be an optional low-resource
browser execution backend for selected MCTL workloads. It would sit behind MCTL's
existing identity, tenant, policy, approval, budget, audit and evidence
boundaries, with Chromium as the fallback. The allowed outcomes are
`ADOPT_LIGHTWEIGHT | HYBRID_FALLBACK | REFERENCE_ONLY | REJECT`. The issue
authorizes only investigation and a proposed report: no harness, no benchmark
execution, no Cloudflare account mutation, no deployment and no pilot.

This matters because the first inventory found no MCTL platform-owned browser
service. Agents reach the web through the `WebFetch`/`WebSearch` tools, which are
`category: network` in mctl-gitops `platform-gitops/agent-platform/policy.yaml`.
The only deployed headless Chromium observed is a tenant workload,
`namax66/news-factory`, and it runs with `NEWS_CHROMIUM_SANDBOX: "false"`. A
backend comparison therefore needs a workload inventory before it needs a
benchmark. Following the repo's spike convention (`AGENTS.md` "Spikes" index,
`roadmap/spikes/*.yaml`, `docs/spikes/*.md`), the deliverable is a report plus a
`SpikeDefinition` manifest at `lifecycle: proposed`.

## User stories

- AS the platform owner I WANT a source-pinned, evidence-tagged report on Kitesurf vs the current Chromium/fetch paths SO THAT I can choose among the four outcomes without mistaking vendor claims for MCTL measurements.
- AS a security reviewer I WANT a threat model and deterministic negative-test design (SSRF, rebinding, tenant bleed, credential exposure, DOM prompt injection, retention, abuse) with named enforcement owners SO THAT any later adapter work has fixed gates before code exists.
- AS a future implementer I WANT a minimal backend contract, capability-based routing and no-side-effect-replay rules SO THAT an adapter, if ever authorized, is an execution adapter under MCTL authority and not a second policy engine.
- AS an operator I WANT a pinned, separately authorizable benchmark protocol with NOT_RUN markers, thresholds and cost model SO THAT no measurement runs without explicit approval and UNKNOWN is never read as PASS.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL pin the upstream sources: `cloudflare/kitesurf` HEAD commit `4a2903813a22b08d4f3cc64a4b35339d0293a5d1` (resolved via `git ls-remote` on 2026-11-14), license Apache-2.0, the blog post (structured date 2026-11-13) and kitesurf.dev/benchmarks (last run 2026-11-13 02:28 UTC). It SHALL also pin the MCTL commits it read (mctlhq/.github `378ac2f370362d52b74f8a8cc36ca402c12e4890`, mctl-gitops `68d6cedbfd5daa244b9f06c14f474029a1c2f40a`), each with source type and freshness.
- WHILE any statement concerns Kitesurf performance, compatibility or cost THE SYSTEM SHALL tag it `[VENDOR]` and keep it separate from `[CODE]`, `[DEPLOYED]` and `NOT_RUN` evidence. No vendor number may appear in a column labelled observed.
- WHEN the report describes current MCTL browser and web paths THE SYSTEM SHALL provide a per-workload matrix (owner, tenant/principal propagation, auth/consent, approval, budget, trace, evidence, feature coverage). Each cell SHALL be VERIFIED, UNKNOWN or NOT_RUN, and an unobserved path SHALL be marked UNOBSERVED, never absent.
- WHEN the report maps related work THE SYSTEM SHALL list mctlhq/.github#18, #151, #181, #308, #314, #330, mctlhq/mctl-agents#1035, mctlhq/mctl-telegram#1088 and mctlhq/mctl-gitops#2544, each with owner and an overlap or no-overlap statement. It SHALL record that no epic, implementation issue or follow-up issue was created.
- WHEN the report specifies the benchmark THE SYSTEM SHALL define the pinned fixtures (anonymous HTML/JS extraction, screenshot/DOM interaction, multi-page synthetic auth/session, explicit unsupported case), metrics (completion %, p50/p95 latency, CPU time, memory peak, concurrency, fidelity, retry/fallback rate, cold start, per-1000-task cost, unsupported-feature rate), thresholds, cost ceiling and failure modes, with every result cell `NOT_RUN`.
- IF a metric or check has no observed value THEN THE SYSTEM SHALL record `UNKNOWN` or `NOT_RUN` and SHALL NOT count it toward any pass threshold or verdict.
- WHEN the report presents the threat model THE SYSTEM SHALL cover SSRF and metadata endpoints, redirects and DNS rebinding, sandbox escape, tenant bleed, cookie/token/session exposure, prompt injection through DOM or screenshot text, data retention, outbound network and usage abuse. Each SHALL have a deterministic negative test and a named enforcement owner.
- WHEN the report presents routing THE SYSTEM SHALL specify capability-based backend selection, refusal when a capability is unsupported, fallback only for read-only operations, no automatic replay of side-effecting operations, idempotency keys, a circuit breaker, and the observation and evidence fields. MCTL SHALL remain the only authority for identity, tenant, policy, approval, budget and audit.
- WHEN the report closes THE SYSTEM SHALL give a four-option decision matrix (A Chromium only, B Kitesurf constrained, C hybrid explicit fallback, D reference-only), with counter-evidence, no-go thresholds and a proposed outcome tied to measured or explicitly missing evidence.
- WHEN the manifest `roadmap/spikes/cloudflare-kitesurf.yaml` is added THE SYSTEM SHALL keep `lifecycle: proposed` with no `decision` block, and `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` SHALL pass.
- IF the work would execute a benchmark, deploy Kitesurf, mutate a Cloudflare account, browse authenticated or uncontrolled public sites, or touch runtime code THEN THE SYSTEM SHALL NOT do it, and SHALL record the step as `NOT_RUN (requires separate authorization)`.

## Out of scope

- Any harness, prototype, adapter code, benchmark execution, `wrangler` deploy, Workers Paid or Dynamic Workers usage, Cloudflare Access configuration or other Cloudflare account mutation.
- Runtime changes in mctl-api, mctl-agents, mctl-telegram, mctl-gitops or any tenant service. This includes `namax66/news-factory`, which is tenant-owned; its `NEWS_CHROMIUM_SANDBOX: "false"` setting is only reported as an observation.
- Real user accounts, cookies, tokens, customer data, live authenticated browsing or automation of uncontrolled public sites.
- Creating epics, implementation issues, follow-up issues, labels, feature flags or approvals, or recording a `decision` block. The owner records the verdict.
- Redefining AgentDefinition/ExecutionProfile ownership (#18), Web Bot Auth egress signing (#308), the Dapr executor boundary (#314) or the preview browser/a11y rollout scope (#330, gitops#2544).

## Open questions

- Upstream detail beyond the README, blog and benchmark page (CDP domain coverage list, WebMCP surface, Web Platform Tests pass rate, third-party dependency notices) was not read at the pinned commit. The report records these as UNKNOWN, to be filled from the pinned tree before any benchmark is authorized.
- No MCTL platform-owned browser workload was observed. If the owner knows of a planned governed browser capability (for example in mctl-agents, mctl-telegram managed runtime or support agent), its task classes would change the matrix. The report assumes none exists and recommends the outcome on that basis.
- Whether the tenant-owned `namax66/news-factory` Chromium usage is in scope as a "selected MCTL workload" is ambiguous. The report treats it as a tenant workload for inventory only, not a candidate the platform may migrate.
- The playwright fixtures for #330/gitops#2544 were not located in the clones available to this run. Their reuse is recorded as UNKNOWN.
- Cloudflare Dynamic Workers per-request pricing at the pinned date was not read. The per-1000-task cost model is a formula with UNKNOWN inputs.
