# Isolated media-engine evaluation harness (X0-X3) under experiments/media-engine-evaluation/

## Context
Issue #128 is a child of #127 revision 2 (proposal `platform-gitops/agents-state/seerrsense/proposals/issue-127-spike-media-competitive-landscape-and-mc/`, design blob `b0bbb7448c29c5a0c880cf8ffef8c38ee5c234d4`, tasks blob `f73fefa988d192f52b78172640a877ea91ac4f4d`; both hashes were re-verified with `git hash-object` during this investigation). #127 scored a decision matrix (Baseline/A/B/C/D/H) whose pivotal inputs (engine safety, measured footprint, parser quality) are all unmeasured, and it defined gates G1-G6 and experiments X1 (isolated benchmark and security probe) and X2 (parser corpus). The owner authorises only the construction of an isolated, opt-in research harness that can produce that evidence. #127 stays proposed/HOLD. This is not an engine selection, not an approval of F1-F6, and not adoption.

The harness lives in a new directory `experiments/media-engine-evaluation/` in the seerrsense repo. It has no runtime dependency on, and makes no change to, the SeerrSense application (`src/`, `public/`, `Dockerfile`, `package.json`, `tsconfig.json`, `.github/workflows/*`, `release-please-config.json`). It delivers: an owner-run baseline inventory (X0), a sandboxed benchmark and probe runner for four configurations (X1), an executable parser comparison over a synthetic corpus (X2), and a reproducible decision-matrix report generator (X3). Wherever native execution is not safely possible, the harness records BLOCKED or NOT RUN with evidence, never a fabricated number.

## User stories
- AS the owner I WANT a read-only local inventory script SO THAT I can supply host baseline data myself without granting anyone access to my Mac or NAS.
- AS a reviewer I WANT every candidate pinned by tag, commit and image digest, resolved by a separate preflight SO THAT results are attributable and nothing is guessed.
- AS the owner I WANT benchmarks to run only in disposable, egress-denied compose projects SO THAT no real tracker, downloader, metadata service or household data is touched.
- AS a reviewer I WANT parser accuracy measured against an independently authored expected-label manifest SO THAT engine parsers are compared on the same ground truth.
- AS the decision maker I WANT the #127 matrix recomputed from machine-readable results with unknowns kept visible SO THAT no winner is forced on missing evidence.
- AS a seerrsense maintainer I WANT the harness fully isolated from the app's build, tests and release SO THAT `npm test`, `npm run typecheck`, the Docker image and release-please are unaffected.

## Acceptance criteria (EARS)

### Isolation from the application
- WHILE the harness exists THE SYSTEM SHALL keep every changed file under `experiments/media-engine-evaluation/` and SHALL not modify `src/`, `tests/`, `public/`, `scripts/`, `Dockerfile`, `package.json`, `package-lock.json`, `tsconfig.json`, `.github/`, `release-please-config.json` or `.release-please-manifest.json`.
- WHILE the harness exists THE SYSTEM SHALL use only the Node.js 22 standard library for its own code (no `npm install`, no `package-lock.json` in the experiment directory), plus pinned container images invoked by its scripts.
- WHEN `npm test` runs at the repository root THE SYSTEM SHALL collect no harness test file (harness tests are named `*.harness-test.mjs`, which vitest's default `**/*.{test,spec}.?(c|m)[jt]s?(x)` include does not match), and the root suite SHALL pass unchanged.
- WHEN the SeerrSense image is built from `Dockerfile` THE SYSTEM SHALL contain no harness file (the Dockerfile copies only `src/`, `public/`, `package*.json`, `tsconfig.json`).

### X0 baseline inventory
- WHEN the owner runs `bin/inventory.sh` THE SYSTEM SHALL record host OS, architecture, total RAM, container runtime and VM size, running container names, image references and digests, and per-container RSS/CPU and host swap, using only local read-only commands, and SHALL write a JSON file conforming to `schema/inventory.schema.json`.
- IF a value cannot be read THEN THE SYSTEM SHALL record it as `{"status":"not_observed","reason":...}` and never as zero or empty.
- WHILE running the inventory THE SYSTEM SHALL not open network connections, read container volumes, environment variables, configuration files, credentials or media paths, and SHALL print the collected JSON for owner review before anything is shared.
- WHILE developing and testing the harness THE SYSTEM SHALL not depend on any inventory from the owner's host; inventory input is optional for X3.

### X1 preflight
- WHEN `bin/preflight.mjs` runs THE SYSTEM SHALL resolve, for each candidate in `candidates.json` (current Seerr/Radarr/Sonarr/Prowlarr baseline, HolyArrs 1.2.0, Streamline v3.4.0, Mediarium v4.1.0, and Reelix v0.8.7 for X2), the tag to a commit SHA and each image reference to a registry digest through anonymous public APIs, and SHALL compare them with the pins in `candidates.json`.
- IF a resolved tag commit or image digest differs from the pin, or cannot be resolved THEN THE SYSTEM SHALL mark that candidate BLOCKED with the observed evidence and SHALL not substitute another tag or `latest`.
- WHEN preflight acquires images and source archives THE SYSTEM SHALL do so without credentials and SHALL record the compressed registry size per image; acquisition SHALL be a separate step from execution.

### X1 runtime isolation
- WHEN `bin/run-x1.mjs` starts a candidate THE SYSTEM SHALL first run the isolation self-test and SHALL refuse to start the candidate (fail closed) unless all of these are demonstrated: every compose network is `internal: true` with IPv6 disabled; no service uses `network_mode: host`, `privileged`, added capabilities, `pid: host`, a Docker socket mount, or any bind mount outside a freshly created run root; and a probe container on the candidate network fails to reach an external IPv4 address, an external IPv6 address, `host.docker.internal` and the host gateway.
- WHILE a candidate runs THE SYSTEM SHALL provide only local fixture services (synthetic Torznab, mock qBittorrent WebAPI v2, mock Jellyfin, local metadata stub) and SHALL log every DNS query and connection attempt that reaches the egress sink as an attempted-egress record.
- WHEN a run ends or is interrupted THE SYSTEM SHALL remove only resources labelled `io.mctl.experiment=media-engine-evaluation` with the run's id, and the run root it created.
- IF a candidate cannot initialise offline through a supported API or documented fixture adapter THEN THE SYSTEM SHALL record BLOCKED with logs and the failing step, and SHALL not patch the candidate, bypass isolation, or report a mock-only result as engine performance.

### X1 measurement
- WHEN a full run executes THE SYSTEM SHALL sample per-container RSS and CPU every 5 s for 10 min idle after warm-up and 30 min of the matched workload (500 synthetic movies, 50 synthetic series), and record VM overhead as a separate series not added to container RSS.
- WHEN smoke mode is selected THE SYSTEM SHALL label every result `mode: "smoke"`, and X3 SHALL not use smoke results for footprint scores.
- WHEN a result is written THE SYSTEM SHALL include host/arch, candidate version, commit and digest, timestamp, workload hash, repetition index, metric source, sampling interval, units and the raw samples, conforming to `schema/result.schema.json`.
- WHEN probes G1-G6 run THE SYSTEM SHALL record each as one of `pass`, `fail`, `blocked`, `not_applicable` (with rationale) or `not_run`, and SHALL never collapse `not_run` or `blocked` into `fail` or `pass`.
- WHILE G3 probes run THE SYSTEM SHALL use only the candidate's supported OAuth/API mechanisms against its fixture instance and SHALL redact tokens, codes and keys from all output.

### X2 parser comparison
- WHEN `bin/gen-corpus.mjs --seed <n>` runs THE SYSTEM SHALL produce at least 150 deterministic release names covering Cyrillic and Latin titles, transliteration, audio markers DUB/MVO/DVO/AVO/Rus+Eng, resolution, codec, edition, season/episode and season packs, ambiguous and negative cases, byte-identical for the same seed.
- WHILE the corpus exists THE SYSTEM SHALL keep the expected labels in a separately authored file `corpus/expected-labels.json` (not produced by the generator) and size in fixture metadata, never inferred from name tokens.
- WHEN a parser is scored THE SYSTEM SHALL report per-field accuracy and coverage, critical false positives (wrong language, wrong dubbing type, wrong season/episode, wrong title on a negative case), an error taxonomy and the reproducer id of every miss.
- WHEN an upstream parser is exercised THE SYSTEM SHALL run it from the pinned upstream source in a network-less container through a thin adapter, and IF no comparable parser interface exists at the tag THEN THE SYSTEM SHALL record `not_comparable` with the path checked, not zero accuracy.

### X3 decision matrix
- WHEN `bin/report.mjs` runs THE SYSTEM SHALL recompute options Baseline/A/B/C/D/H with weights fit 25, safety 20, effort 20, footprint 15, license 10, migration 10 and scenarios s0-s3 from #127, output point totals and [low-high] ranges, and list deltas and ranking reversals against #127 revision 2.
- IF a criterion lacks measured evidence THEN THE SYSTEM SHALL keep the revision-2 prior marked `provisional` and SHALL not declare a leader where ranges overlap.
- IF any G1-G6 result for a candidate is `fail`, `blocked` or `not_run` THEN THE SYSTEM SHALL show it in the report and SHALL state "experiment result only, no adoption recommendation".
- WHEN the report is generated from `examples/synthetic-results/` THE SYSTEM SHALL label every page "SYNTHETIC EXAMPLE DATA - not measured".

## Out of scope
- Running X1 on the owner's Mac mini or NAS, or reading any household system, volume, credential or media.
- Selecting or adopting an engine, creating `mctl-media`, implementing #127 features F1-F6, or any change to SeerrSense runtime, MCP tool registry, auth, migrations, GitOps, release configuration or production workflows.
- A CI job for the harness (adding one would edit `.github/workflows/`); smoke checks are owner/reviewer-run commands.
- Copying or vendoring upstream (AGPL/GPL) code into the repository.
- Engines beyond the five named (Reelix only in X2).
- Fixing the `LICENSE` (MIT) vs `package.json` (ISC) mismatch noted in #127.

## Open questions
- Baseline image pins: #127 does not record which Seerr/Radarr/Sonarr/Prowlarr images or versions the household runs (the owner host was never observed). Proposed: pin the current upstream stable releases (`ghcr.io/seerr-team/seerr`, `lscr.io/linuxserver/radarr`, `.../sonarr`, `.../prowlarr`) resolved by preflight, labelled "reference baseline, not owner baseline"; X0 lets the owner substitute their own digests later.
- Image availability for HolyArrs, Streamline and Mediarium at the exact tags is not verified here (no registry access in this run). If a tag has no published image, the candidate is BLOCKED unless the owner approves a local source build at the pinned commit; the proposal treats a source build as allowed only through the upstream's own Dockerfile at that commit and labels it `built_from_source`.
- Upstream parser adapters (Go for HolyArrs/Streamline/Mediarium, Rust for Reelix) import copyleft packages. The adapter source is MCTL-authored and the combined binary is built and run only locally, never distributed. Reviewer should confirm this is an acceptable licence boundary; otherwise adapters fall back to each upstream's own test command where it exposes one.
- The exact parser entrypoints named in #127 (`internal/core/releasename/parse.go`, `internal/library/parser.go`, `internal/parser/parser.go`, `crates/reelix-parser`) are taken from #127's tree reads and must be re-verified at tag by task 9; Go `internal/` packages cannot be imported from an outside module, so adapters are placed inside the upstream checkout copy at build time (see design).
- No approved isolated runtime for executing candidates is known for this repo. Full native runs may remain NOT RUN; the PR must say so.
