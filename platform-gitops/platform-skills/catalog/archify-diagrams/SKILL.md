---
name: archify-diagrams
description: "Author, validate and render system diagrams as typed JSON with archify (architecture, workflow, sequence, dataflow, lifecycle). Use when a change touches orchestrator/temporal/, an ADR, an operation→CWFT mapping, or any docs/diagrams/archify/*.json, and when asked to visualise a component map, a runbook, a call sequence or a state machine for an mctlhq repository."
user-invocable: true
---

# Archify diagrams

Diagrams in mctlhq repositories are code: a small JSON file next to the code
it describes, validated in CI like the code. Mermaid (`docs/diagrams/*.mmd`)
stays for pages GitHub renders itself; archify JSON is for anything that will
be presented, exported or embedded.

## Where things live

| What | Path |
| --- | --- |
| Diagram sources | `docs/diagrams/archify/<name>.<type>.json` — type ∈ `architecture`, `workflow`, `sequence`, `dataflow`, `lifecycle` |
| archify toolkit | `/opt/archify` in the mctl-agents image (pinned commit); locally `git clone https://github.com/tt-a1i/archify && (cd archify/archify && npm install)` |
| CI | `.github/workflows/diagrams.yml` — `validate --quality showcase` on every PR, `deliver` + `visual-check` on `main` |
| Rendered HTML | never committed; CI uploads it as a job artifact |

Set `ARCHIFY=/opt/archify/archify/bin/archify.mjs` (or the local clone) and
`ARCHIFY_CHROME` to a Chromium binary when running `visual-check`.

## Authoring loop (bounded — do not read renderer source)

1. Pick the type from the question: components and boundaries → `architecture`;
   a process with lanes, gates and exceptions → `workflow` (`schema_version: 2`);
   a call chain with time → `sequence`; a state machine → `lifecycle`;
   a pipeline with stages → `dataflow`.
2. Read exactly one schema (`/opt/archify/archify/schemas/<type>.schema.json`),
   `common.schema.json`, and one matching example from `/opt/archify/archify/examples/`.
   Copy the field shape, never the facts.
3. Write the candidate first. `meta.quality_profile` must be `"showcase"`.
   At most 12 primary nodes, one obvious main path, sparse labels, fresh stable ids.
   Omit `meta.visual_preset`, `meta.subtitle`, `meta.legend`, `meta.locale`.
4. Validate after every edit:
   `node $ARCHIFY validate <type> <file> --quality showcase --json`
   A pass reports 9/9 artifact checks, 0 errors, 0 warnings. Fix only the
   `subject` a diagnostic names, choose from its `supportedFixes`, re-run.
   Stop and report truthfully if two rounds do not lower the error count.
5. Deliver once for acceptance:
   `node $ARCHIFY deliver <type> <file> <out>.html --quality showcase --json`
   then `node $ARCHIFY visual-check <out>.html --json` when Chromium is available.
   A non-zero exit is never a success.

## mctl-specific rules

- Every node and label must be traceable to a file, constant or ADR in the
  target repository. Name the source in a card (`docs/adr/006`, `run_shepherd.py`).
  Never draw a component that does not exist yet without a `tag: "design"`.
- Preserve exact identifiers: CWFT names (`mctl-agents-implement`), status values
  (`review-fixing`), MCP tool names (`mctl_approve_dev_loop`), env vars, paths.
- Sub-labels must stay short (≈ 20 characters) — the showcase readability check
  fails on 1440 px desktops otherwise. Put detail in `tag` or in cards.
- Brands: use only ids from `node $ARCHIFY brands "<name>" --json`
  (`claude`, `github`, `postgresql`, `grafana`, `argo`, `kubernetes`, …). Never guess.
- Workflow v2 has six columns (`col` 0–5) and a lane band; place nodes by lane
  and column, never by pixel. Prefer automatic routing; add a `route` or `via`
  only after a diagnostic asks for one. Vertical edges across a lane gap cannot
  carry labels longer than ≈ 6 characters.
- Lifecycle: lanes other than `main`/`terminal` share one band; column `N` of a
  side lane sits beneath main column `N + 2`. A `failure` state that can recover
  needs a real transition back to an active state.
- Sequence: `y` values must stay inside the readable timeline (≈ 160 … viewBox
  height − 90). Use `column_fit: "spread"` for long participant names.
- Commit the JSON with a Conventional Commit (`docs(diagrams): …`); never commit
  rendered HTML or PNGs. No `Co-Authored-By` trailer.

## Definition of done

- `validate --quality showcase --json` → `ok: true`, 9/9 checks.
- Every card item is a fact with a source, not a slogan.
- The diagram's `meta.views` tell the story in ≤ 3 guided chapters.
