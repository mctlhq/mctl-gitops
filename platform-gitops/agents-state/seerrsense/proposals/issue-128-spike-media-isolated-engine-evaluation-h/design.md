# Design: issue-128-spike-media-isolated-engine-evaluation-h

## Current state

### Repository (clone at da0c5a3, seerrsense 1.14.4)
- Top level: `src/`, `tests/`, `public/`, `scripts/sync-tokens.mjs`, `docs/portal-allowlist.json`, `Dockerfile`, `package.json`, `tsconfig.json`, `release-please-config.json`, `.release-please-manifest.json`. There is no `experiments/` directory, so the new path collides with nothing.
- `package.json` `"test"` is `vitest run`, and there is no vitest config file. Vitest's default include, `**/*.{test,spec}.?(c|m)[jt]s?(x)`, therefore applies to the whole tree. A `*.test.mjs` placed under `experiments/` would be collected by `npm test` and by the "Test" step in `.github/workflows/ci.yml`. Harness tests must not use that naming.
- `tsconfig.json` sets `"rootDir": "./src"` and `"include": ["src/**/*"]`, so `npm run typecheck` never sees `experiments/`.
- `Dockerfile` copies only `package.json`, `package-lock.json*`, `tsconfig.json` and `src/` into the builder, then `dist` and `public/` into the runtime. There is no `COPY .`, so harness files never enter the image.
- `tests/source-hygiene.test.ts` scans only `src/` and `tests/` for control characters. The harness needs its own equivalent check, which matters for a Cyrillic corpus.
- `tests/bake-off.ts` is precedent for an opt-in research script that vitest does not collect. It has no `.test.` in its name and runs by hand. Unlike bake-off, which calls Nebius, harness tests make no network call.
- `release-please-config.json` sets `release-type: node` on package `.`. Any `feat` or `fix` commit bumps the app, so harness commits are `chore(experiments)` or `test(experiments)`.
- CI (`ci.yml`) runs `check:tokens`, typecheck, `npm test` against Postgres, and `docker build`. None of these touches the harness while the naming rule above holds. `claude-review.yml` and `agent-trailer-check.yml` run on every PR. They are review aids, not merge automation.
- Toolchain: Node 22 (`setup-node` 22 in CI, `node:22-slim` image; v22.23.5 in the investigation sandbox). The sandbox has no Docker.

### Parent inputs (#127 revision 2; blobs verified with `git hash-object`)
- Design blob `b0bbb744...` and tasks blob `f73fefa9...` match the issue. Parent `.status.yaml` reads `status: proposed`, `requires_human_approval: true`. This proposal does not touch it.
- Matrix in parent section 2:
  - six options: Baseline, A, B (HolyArrs), C (Streamline), D (Go engine), H (hybrid, replaces Radarr first);
  - 1-5 cell scores with [low-high] ranges;
  - weights 25/20/20/15/10/10;
  - scenarios: s1 footprint 30/fit 20/effort 15/migration 5; s2 safety 30/fit 20/footprint 10; s3 effort 10/fit 30/footprint 20;
  - s0 point totals: Baseline 3.60, A 3.65, B 3.50, C 3.40, D 2.70, H 2.95;
  - uniform Monte Carlo sampling, 20,000 draws, seed 127;
  - the single-cell rank reversals.
- G1-G6 gate definitions are in parent section 2. The fixture vertical slice is in section 7.

### Upstream pins re-verified in this investigation (GitHub API and anonymous OCI HEAD, 2026-11-22)

| Candidate | Tag | Full commit | SPDX | Parser entrypoint at tag | Image (index digest observed) |
|---|---|---|---|---|---|
| HolyArrs | 1.2.0 | `d63e43f36a3a2babf475624f61b0a11021fd98fc` | AGPL-3.0 | `app/backend/internal/core/releasename/parse.go`: `func Parse(name string, h Hints) Result` | `docker.io/holyarrs/holyarrs:1.2.0` `sha256:169d2c90773011fcdce576e44ff40f71e1ddef18408fc367d870bfa57325323e`. ghcr returned 403, so not on ghcr. |
| Streamline | v3.4.0 | `6d6d255e5b6e662c374aa3b7de98b2a736f50ab5` | GPL-3.0 | `internal/library/parser.go`: `func Parse(filename string) ParseResult`, plus `ParseSeasonSpan` and `IsWholeSeriesPack` | `ghcr.io/datahearth/streamline:3.4.0` `sha256:c5f0b13750c567c7f0d97539826a8271322bc45ab74b18eabb1b8fd430329973`. `:v3.4.0` returned 404. `deploy/compose.yaml` builds from `deploy/Dockerfile`. |
| Mediarium | v4.1.0 | `9ff49c21169b8ac135a3022906e0c961b34bc16c` | AGPL-3.0 | `internal/parser/parser.go`: `func Parse(name string) Release`. Also `language.go`, `mojibake.go` and `internal/download/releasename.go`. | `ghcr.io/rdborg/mediarium:4.1.0` `sha256:4145c9818fb8631cd0508abf6d8cd35581e968909fc3001f946b235508af98b6`. `:v4.1.0` returned 404. |
| Reelix (X2) | v0.8.7 (prerelease) | `606fa714fa939271a086ed89c3695c9492210fd8` | GPL-3.0 | `crates/reelix-parser/src/lib.rs`: `pub use parser::parse;` (`parser.rs`, `episode.rs`, `title.rs`, `tags.rs`) | `ghcr.io/demonzoned/reelix:0.8.7` `sha256:0e281e1b85a7dfbe8f24fecaef8be21695beea5c8e37b66d8e855c005a407a3a`. `:v0.8.7` returned 404. |

Findings that shape the design:
- Git tags carry a `v` prefix where image tags do not. The manifest therefore stores `tag` and `image.ref` separately and never derives one from the other.
- The digests above are index digests observed once. Whether they were built from the pinned commit is not yet verified, so preflight checks the `org.opencontainers.image.revision` label.
- The Go parsers live in `internal/` packages, which an outside module cannot import. The adapter must be compiled inside a scratch copy of the upstream tree.
- Streamline ships fixture designs at the tag (`e2e/fakes/torznab.go`, `qbittorrent.go`, `tmdb.go`, `torznab_recorder.go`). They are read as reference only, never copied, since they are GPL.
- Reference baseline releases (latest on 2026-11-22): `seerr-team/seerr` v3.5.2, `Radarr/Radarr` v7.0.3.10918, `Sonarr/Sonarr` v4.0.20.3014 and `Prowlarr/Prowlarr` v3.0.2.5780. Their image digests have not been resolved yet; that is task 4.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/seerrsense/values.yaml` (read): image `ghcr.io/mctlhq/seerrsense` tag `1.14.4`, digest `sha256:e65663bf8f1aa5e6bc5999562c725f054717d8189b553398be5d585a5926e485`, host `seerrsense.mctl.ai`, `SEERR_URL=https://media.mctl.ai`. The harness changes nothing here and adds no service.
- `mctl_get_service_status(team=labs, service=seerrsense)`: ArgoCD `labs-seerrsense` Healthy and Synced, imageTag 1.14.4, port 8787, `hasDatabase: true`.
- Not observed: the owner's Mac mini and NAS, where the household stack runs. By design the harness never observes them; X0 is an owner-run input.
- Not observed: whether any approved isolated Docker runtime exists for this work. The sandbox has no `docker`. See Open questions.

## Proposed solution

### Directory layout (all new, under `experiments/media-engine-evaluation/`)
```
README.md                    scope, authorisation boundary, licence boundary, commands, "run vs specified" table
.gitignore                   runs/ out/ .cache/
candidates.json              pinned manifest (see Manifest)
bin/
  inventory.sh               X0, owner-run, read-only, POSIX sh
  preflight.mjs              the only networked step: resolve/verify pins, pull by digest, fetch source tarballs
  isolation-check.mjs        static compose lint + live probe; exit 3 = fail closed
  run-x1.mjs                 disposable per-candidate compose run, sampling, G1-G6 probes
  cleanup.mjs                removes only resources with both experiment labels for a run id
  gen-fixtures.mjs           500 movies / 50 series synthetic metadata + tiny payloads
  gen-corpus.mjs             X2 deterministic names
  run-x2.mjs                 builds/runs parser adapters with --network none, scores
  report.mjs                 X3 matrix + per-candidate report (markdown + JSON)
lib/   prng.mjs schema-validate.mjs redact.mjs stats.mjs compose-lint.mjs labels.mjs
       score.mjs sensitivity.mjs evidence-map.mjs docker.mjs (thin child_process wrapper, injectable)
lib/probes/ g1.mjs ... g6.mjs
schema/  inventory, candidate-manifest, result, parser-result, report (.schema.json)
fixtures/services/  torznab.mjs qbittorrent.mjs jellyfin.mjs metadata-stub.mjs egress-sink.mjs
compose/  base.yml baseline.yml holyarrs.yml streamline.yml mediarium.yml
adapters/x1/<id>/   documented-config fixture adapters (env, config files, API calls)
adapters/x2/<id>/   adapter source + Dockerfile.adapter + field-map.json
corpus/  names.json (generated, committed) expected-labels.json (hand-authored) fixture-sizes.json
priors/rev2-matrix.json      transcribed parent section 2
examples/synthetic-results/  SYNTHETIC sample raw results; examples/sample-report.md (generated)
test/*.harness-test.mjs      node:test, no network
```

### Language and dependencies
The harness uses the Node 22 standard library only: `node:test`, `node:crypto`, `node:http`, `node:dgram`, `node:fs`, and `node:child_process` to call `docker`. This matches the repo toolchain, adds nothing to the root `package.json`, and needs no lockfile. `lib/schema-validate.mjs` validates the JSON Schema subset the harness uses: `type`, `required`, `enum`, `properties`, `items`, `additionalProperties`, `pattern`, `minimum`, `oneOf`. Tests run with `node --test experiments/media-engine-evaluation/test/`. Docker calls go through `lib/docker.mjs` with an injectable executor, so unit tests use a recording shim and never need Docker.

### Manifest (`candidates.json`)
Each entry has these fields:
- `id`, and `role`: `x1`, `x2` or both;
- `repo`, `tag`, `commit` (40 hex);
- `images[]`: `{ref, digest, platform, registry_compressed_bytes, provenance}`;
- `license` (SPDX);
- `sources[]`: primary URLs at the pinned commit;
- `parser`: `{path, entry, lang}`, or `null`;
- `x1_adapter`: the documented config used;
- `upgrade_from`: for G4;
- `status`: `pinned`, `unverified` or `blocked`.

The baseline is one composite entry with four images. The values in the table above are committed. Digests not yet resolved are `null` with `status: unverified`. Only a reviewed edit changes a pin. Preflight never writes the manifest; it writes `out/preflight.json`.

### X0 inventory (`bin/inventory.sh`)
It collects:
- `uname -sm`;
- RAM: `sysctl hw.memsize` on macOS, `/proc/meminfo` on Linux;
- swap: `sysctl vm.swapusage` on macOS, `/proc/meminfo` on Linux;
- runtime: `docker version --format`, `docker info --format '{{.NCPU}} {{.MemTotal}}'`, and `colima list --json` when present;
- containers: `docker ps --format '{{.Names}} {{.Image}}'` and `docker image inspect --format '{{json .RepoDigests}}'` (an image query, not a container inspection);
- usage: `docker stats --no-stream --format json`.

It never runs `docker inspect` on containers (that would expose env and mounts), never runs `docker exec`, never opens a network connection, and never reads home, volume or config paths. Missing commands yield `not_observed`. `--dry-run` prints the command list only. Output goes to stdout, so the owner can review it before saving.

### X1 preflight
`preflight.mjs` resolves each pin as follows:
- tags: anonymous GitHub REST (`/repos/{r}/git/ref/tags/{tag}`, dereferencing annotated tags);
- digests: the OCI distribution API, with anonymous bearer tokens for docker.io, ghcr.io and lscr.io (a HEAD for the index digest, a GET for per-platform manifests and layer sizes, and the config blob for the revision label).

It then pulls with `docker pull ref@digest` and fetches source with `/repos/{r}/tarball/{sha}` into `.cache/src/<id>-<sha>/`. For Go or Rust adapters it also pre-fetches module dependencies, in a pinned toolchain container, into a vendor directory inside `.cache/`. That lets later builds run with `--network none`. Drift or a failed resolution marks the candidate BLOCKED. Preflight runs alone and before any run; `run-x1.mjs` and `run-x2.mjs` refuse to pull or fetch.

### X1 runtime
- Each run gets a run id and, per candidate, a compose project `mee-<runid>-<candidate>`. Its run root `runs/<runid>/<candidate>/` is created with `fs.mkdtemp`. Every container, network and volume carries the labels `io.mctl.experiment=media-engine-evaluation` and `io.mctl.run=<runid>`.
- `compose/base.yml` defines the network `fixture` with `internal: true` and `enable_ipv6: false`, the fixture services, and the egress sink. There are no `ports:` entries; the runner reaches services through `docker compose exec` on a runner sidecar.
- `compose-lint.mjs` checks the output of `docker compose config --format json`. It rejects:
  - `network_mode`, `privileged`, `cap_add`, `devices`, `pid`/`ipc: host` and `ports`;
  - `/var/run/docker.sock`;
  - bind sources whose realpath is outside the run root;
  - non-internal networks and IPv6-enabled networks;
  - `extra_hosts` other than the stub aliases.
- Live probe, run before the candidate starts: a pinned `busybox` (by digest, acquired in preflight) on the network tries TCP to 1.1.1.1:443, `[2606:4700:4700::1111]:443`, `host.docker.internal` and the default gateway. It also tries to resolve `api.themoviedb.org` to a non-sink address. Any success aborts the run with exit code 3. The evidence is stored under `isolation` in the result.
- Egress capture: the sink acts as the network's DNS (`dns:` points at the sink) and answers every name with its own address. It logs the qname and, for each connection, the host, port and first bytes, with secrets redacted. Real hostnames a candidate tries appear as attempted egress; for example, HolyArrs' default `api.holyarrs.com` (parent E6). Documented overrides such as HolyArrs `HOLYARRS_METADATA_URL` point at `metadata-stub.mjs`.
- Fixtures are seeded and generated by `gen-fixtures.mjs`:
  - 500 movie and 50 series records with synthetic titles and ids in a reserved range;
  - Torznab XML (caps, search, rss) that references payload files of 4 KiB or less;
  - a qBittorrent WebAPI v2 mock (`auth/login`, `torrents/add`, `torrents/info`, `torrents/delete`, `app/preferences`). It "completes" a download by writing the tiny file into the run root, and it counts adds per info-hash so duplicate grabs can be detected;
  - a Jellyfin mock (`System/Info`, `Items`, `Library/Refresh`);
  - the metadata stub, a TMDB-shaped subset.

  Fixture designs are informed by Streamline's `e2e/fakes/*` at the tag, read but not copied.
- Candidates are configured only through documented env, configuration or HTTP API (`adapters/x1/<id>/`). There is no image modification, patching or debugger. For the baseline, the adapter configures Prowlarr with the synthetic Torznab indexer, Radarr and Sonarr with the mock qBittorrent, and Seerr with Radarr, Sonarr and the Jellyfin mock, all via their APIs. Anything that cannot be configured offline is BLOCKED, with the failing call recorded.
- Measurement, in `lib/stats.mjs`:
  - Source: `docker stats --no-stream --format json` every 5 s, recorded as `metric_source: docker-stats` (cgroup memory usage minus inactive file). Units are bytes and percent of one CPU.
  - Phases: warm-up (until healthy, plus 60 s), idle 600 s, active 1800 s.
  - Workload: add all 500 movies and 50 series, trigger searches, grabs and imports, refresh the library. The workload hash is SHA-256 of the fixture set plus the script.
  - Latency p50/p95 per API operation.
  - VM overhead is a separate series, from `colima`/`docker info` totals minus the sum of containers. It is never added to container RSS. Fixture and runner containers are reported apart from the candidate.
  - Image size: compressed bytes from preflight vs unpacked bytes from `docker image inspect --format '{{.Size}}'`.
  - Smoke mode: 30 s idle and 60 s active over 20 movies and 2 series, labelled `mode: smoke`.
- Probes return `{gate, status, evidence, rationale}`:
  - G1: 50 vertical-slice runs (parent section 7). Pass requires at least 49 successes, zero duplicate adds per hash, and zero files outside the run root (walk plus realpath).
  - G2: `docker kill -s KILL` during download and during import, 10 times each, followed by a reconcile check. Disk-full uses a size-limited tmpfs volume inside the project. Backup/restore uses the candidate's documented mechanism onto a fresh volume.
  - G3: covers plain-PKCE refused, unregistered redirect refused, single-use code, revoked key refused, a single-use and user-bound confirm token, and the DCR rate limit. These run only where the tag exposes them through a supported switch (HolyArrs `ai_apps`, Mediarium MCP). Elsewhere G3 is `not_applicable` with rationale, or `blocked` if the switch has no documented API. A dependency advisory scan runs on the fetched source (offline, from a pinned database snapshot acquired in preflight) along with signature/attestation checks; if they cannot run, they are `not_run`.
  - G4: upgrade from `upgrade_from` to the pinned tag on the fixture DB, then the documented rollback. Without an `upgrade_from` pin, G4 is `not_run`.
  - G5: computed only from full-mode measured series, as the candidate against the matched baseline subset it replaces. The 30% target is evaluated, not assumed.
  - G6: provenance, licence, security contact, and observed vs documented egress.
- Cleanup: `cleanup.mjs --run <id>` runs `docker compose -p <project> down -v --remove-orphans` for projects it created. It then removes leftovers filtered by both labels, and `rm -rf` on the run root, but only after a realpath check that the root is under `runs/`. It never prunes. `run-x1.mjs` traps SIGINT/SIGTERM and calls it.

### X2 parser comparison
- `gen-corpus.mjs` uses a seeded mulberry32 PRNG over templates to write `corpus/names.json`: at least 150 entries of `{id:"P###", name, class[]}`. The classes are Cyrillic, Latin, transliterated, DUB, MVO, DVO, AVO, Rus+Eng, studio-tag, resolution, codec, source, edition, single-episode, multi-episode, season pack, whole-series pack, ambiguous year/number titles, and negative (not a video release). Each class has at least 5 entries.
- `corpus/expected-labels.json` is hand-authored per id, independently of the generator. Its fields are: `title`, `year`, `audio_languages[]`, `dubbing_type` (`dub|mvo|dvo|avo|original|unknown`), `resolution`, `codec`, `edition`, `season`, `episodes[]`, `pack` (`none|season|series`) and `negative`. Each field carries `confidence: confirmed|unknown`. Sizes live in `corpus/fixture-sizes.json`.
- Adapters live in `adapters/x2/<id>/`. Each is an MCTL-authored stdin-to-JSON-lines program plus `field-map.json`, which maps upstream fields to label fields, with `unsupported` for fields an upstream does not emit.
  - Go (HolyArrs, Streamline, Mediarium): the adapter is copied at build time into the scratch tree `.cache/build/<id>/` as `cmd/mee-adapter/main.go`. That places it inside the upstream module, so `internal/` imports are legal. It is built with `go build -mod=vendor` in a pinned `golang` image with `--network none`.
  - Rust (Reelix): a scratch crate with a path dependency on `crates/reelix-parser`, built with `cargo build --offline`.
  - Before building, `run-x2.mjs` checks that the entry path and the exported symbol from the table above exist. If not, the result is `not_comparable` with the evidence. HolyArrs' `Parse` takes `Hints`; the adapter passes zero-value hints and records that in `field-map.json`.
- Scoring, in `lib/labels.mjs`:
  - accuracy = correct / (labelled `confirmed` and emitted);
  - coverage = emitted / labelled;
  - `unsupported` fields are excluded, not counted as wrong;
  - critical false positives are: a language or dubbing type asserted on an `unknown` label or a different one; a wrong season or episode; a pack misclassified; any title emitted on a negative.
  - Taxonomy codes (`E-LANG`, `E-DUB`, `E-SE`, `E-PACK`, `E-RES`, `E-CODEC`, `E-EDITION`, `E-TITLE`, `E-TRANSLIT`, `E-NEG`) each list reproducer ids.
- Licence boundary: upstream code is executed, not copied. The adapter binaries exist only in `.cache/`, which is ignored by git and never distributed. The README states this.

### X3 report
- `priors/rev2-matrix.json` is a transcription of parent section 2. A test asserts that it reproduces the parent totals for s0-s3.
- `lib/evidence-map.mjs` holds pure, documented rules:
  - measured full-mode G5 replaces the footprint cell for B and C (Mediarium as B'), and informs H through Radarr's measured share;
  - G2/G3 outcomes adjust safety, using the parent's own example: a confirm-token replay or DCR abuse sets safety to 2;
  - the X2 critical false-positive rate informs the fit range for D and H;
  - any cell without qualifying evidence keeps its prior and is tagged `provisional`.
- `report.mjs` outputs, per scenario:
  - point totals and [low-high] ranges;
  - Monte Carlo first-place shares (20,000 draws, seed 127);
  - a leader only if its low bound exceeds every other option's high bound, otherwise "no leader (ranges overlap)";
  - deltas vs revision 2, and rank reversals;
  - a gate table per candidate;
  - three separate sections: engine selection, implementation choice (unmodified, fork, clean-room) and integration choice (topology T1/T2, SeerrSense adapter);
  - an "Experiment GO" column distinct from "Business/adoption GO", which stays DEFERRED while any gate is not `pass`.
- With `--synthetic` input, every section carries the SYNTHETIC banner. `examples/sample-report.md` is generated from `examples/synthetic-results/` and committed, and a test regenerates it byte-for-byte.

### What is run vs specified
The README table, filled in by the implementer:

| Part | When it is run |
|---|---|
| Unit tests, synthetic report | Run in the PR |
| Preflight | Run where network access is available; output attached to the PR |
| X0 | Specified only; the owner runs it |
| X1 smoke | Only in an approved isolated Docker environment, otherwise NOT RUN |
| X1 full | NOT RUN by default |
| X2 adapters | Run if preflight and toolchain images are available, otherwise NOT RUN |

## Alternatives
- A new repo (`mctlhq/mctl-media-eval`). Dropped: the issue forbids a new repo, and the parent defers `mctl-media`.
- TypeScript with vitest, reusing the app toolchain. Dropped: `experiments/` is outside `tsconfig.json` `rootDir`, and `*.test.ts` would be collected by the root `npm test` (there is no vitest config). Either the root config would have to change, or the app suite would be polluted.
- Python or Go for the harness itself. Dropped: that adds a toolchain and third-party dependencies the repo does not use. Go and Rust appear only inside the upstream adapter builds, where they are unavoidable.
- Reimplementing upstream parser rules in a wrapper. Dropped: it would be a fabricated result and would risk copying copyleft logic.
- Host firewall or network-namespace isolation. Dropped: it needs root and host changes. Compose internal networks, a sink resolver and a live probe are demonstrable without touching the host, and they fail closed.

## Platform impact
- Migrations: none. There is no schema, GitOps, tenant or service change; `labs/seerrsense` stays at 1.14.4.
- Backward compatibility: application code, tests, image and MCP tools are untouched. Root `npm test`, `npm run typecheck`, `check:tokens` and `docker build` behave identically, which task 13 verifies.
- Release: `chore(experiments)` and `test(experiments)` commits only. No auto-merge, release or deploy.
- Resources: none in the cluster. Locally, a full X1 run needs Docker and roughly the footprint of each candidate stack, sequentially, for about 45 min per candidate per repetition. Smoke mode takes a few minutes.
- Risks and mitigations:

| Risk | Mitigation |
|---|---|
| Candidate egress | Internal networks, sink DNS, live probe, fail closed |
| Cleanup touching unrelated resources | Two-label filter plus project prefix and a realpath check; no prune |
| Smoke or synthetic data mistaken for evidence | Required `mode` and `synthetic` fields; the evidence map refuses them |
| Copyleft contamination | Scratch builds in `.cache/`, plus a test that no upstream file or copyright header is committed |
| Stale pins (HolyArrs releases daily) | Preflight blocks on drift |
| Image not built from the pinned commit | Revision-label check, labelled `built_from_source` fallback |
| Control characters in the Cyrillic corpus | Harness-local hygiene test |
