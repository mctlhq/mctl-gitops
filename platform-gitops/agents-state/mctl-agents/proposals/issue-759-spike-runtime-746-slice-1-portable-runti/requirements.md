# Portable-runtime spike, slice 1: experiment scaffolding and isolation test

## Context
Spike mctlhq/mctl-agents#746 explores a portable single-binary runtime written in Rust. Its DevLoop ended `Failed` because the implementer image has no `cargo`, no network and no credentials, so nothing Rust-dependent could be produced. Issue #759 carves out the part the implementer image can produce and verify with Python alone: an inert Rust crate skeleton under `experiments/portable-runtime-rs/`, a pytest isolation test proving the experiment cannot leak into the shipped image or orchestrator, the ignore-file and commit-lint plumbing, and an optional, non-required GitHub Actions workflow where the Rust build itself is verified.

The point of the slice is containment: slice 2 (the actual Rust bridge, bench and report) will land many Rust files, and the isolation test plus the dedicated workflow must exist first so that slice 2 is verifiable and provably cannot change what `Dockerfile` ships.

## User stories
- AS a platform maintainer I WANT the Rust spike confined to `experiments/portable-runtime-rs/` SO THAT it cannot change the production image, the orchestrator or any agent manifest.
- AS the slice-2 implementer I WANT a committed crate skeleton and a CI workflow that runs `cargo build/test/clippy/audit` SO THAT Rust changes are verified somewhere even though the implementer image has no cargo.
- AS a PR author touching only tests, docs, CI or experiments I WANT commit-lint to treat `experiments/` as non-shipping SO THAT spike-only PRs do not need a releasable commit.

## Acceptance criteria (EARS)
- WHEN the change is merged THE SYSTEM SHALL contain `experiments/portable-runtime-rs/` with `Cargo.toml`, a committed `Cargo.lock`, `rust-toolchain.toml`, `README.md` and `src/main.rs`, and no other Rust source.
- WHEN the built binary is run THE SYSTEM SHALL print its name and the crate version (`env!("CARGO_PKG_VERSION")`) and exit 0.
- THE SYSTEM SHALL mark `experiments/portable-runtime-rs/README.md` as EXPERIMENTAL and default-off, and document how to build/run it and how to delete it.
- WHEN `uv run --locked pytest -q` runs THE SYSTEM SHALL execute `tests/test_portable_runtime_isolation.py` and pass.
- WHILE `experiments/portable-runtime-rs/` exists THE SYSTEM SHALL fail the isolation test if any file under `orchestrator/`, `config/` or `agents/`, or any of `Dockerfile`, `entrypoint.sh`, `pyproject.toml`, `uv.lock`, contains the string `experiments/` or `mctl-runtime`.
- WHILE `experiments/portable-runtime-rs/` exists THE SYSTEM SHALL fail the isolation test if `Dockerfile` contains a `COPY`/`ADD` instruction whose source references `experiments`.
- WHILE `experiments/portable-runtime-rs/` exists THE SYSTEM SHALL fail the isolation test if `.dockerignore` does not exclude `experiments/`.
- WHILE `experiments/portable-runtime-rs/` exists THE SYSTEM SHALL fail the isolation test if a `Cargo.toml` exists anywhere in the repository outside `experiments/portable-runtime-rs/` (ignoring `.git/`, `.venv/`, `venv/`, `_gitops/` and `target/` directories).
- IF `experiments/portable-runtime-rs/` is absent THEN THE SYSTEM SHALL skip the isolation checks (reported as skipped, not failed).
- WHEN the negative self-check runs THE SYSTEM SHALL feed the Dockerfile detector the real `Dockerfile` text plus an appended `COPY experiments/ ./experiments/` line and assert that the detector flags it; this self-check SHALL run even when the experiment directory is absent.
- THE SYSTEM SHALL list `experiments/**/target/` in `.gitignore` and `experiments/` in `.dockerignore`.
- WHEN commit-lint in `.github/workflows/pr-validation.yml` classifies changed paths THE SYSTEM SHALL use `SHIPPING_PATHS='^(tests/|docs/|\.github/|experiments/)'`.
- WHEN a pull request changes `experiments/portable-runtime-rs/**` or the spike workflow file, or the workflow is dispatched manually, THE SYSTEM SHALL run `.github/workflows/portable-runtime-spike.yml` on `ubuntu-latest` and `macos-14`, executing `cargo build --locked`, `cargo test --locked`, `cargo clippy --locked --all-targets -- -D warnings` and a dependency audit step.
- WHILE the spike workflow runs THE SYSTEM SHALL use `permissions: contents: read`, actions pinned to full commit SHAs (as in `pr-validation.yml`), and SHALL NOT be configured as a required status check.
- WHILE this change is applied THE SYSTEM SHALL leave `orchestrator/`, `config/`, `agents/`, `Dockerfile`, `entrypoint.sh`, `pyproject.toml` and `uv.lock` byte-identical, so the `docker-build` smoke job produces the same image contents.

## Out of scope
- Any Rust logic beyond printing the version: the bridge, credential sources, correlation, fake upstream, Python baseline, benchmarks, cross-builds and the decision report (all slice 2).
- Making the spike workflow a required check, or any branch-protection change.
- Any change to the orchestrator, image, agent manifests, CWFTs, or deployed workers in mctl-gitops.
- Closing or editing #746, its proposal, or its consumed approval grant.
- Fixing the mctl-api DevLoop restart gap that motivated the slicing.

## Open questions
- Commit-lint classification of this PR itself: `.gitignore` and `.dockerignore` sit at the repo root and are outside the new `SHIPPING_PATHS`, so this PR still counts as shipping and needs a `feat`/`fix`/`perf`/`revert` commit subject or commit-lint fails. Proposed interpretation: use a `feat(experiments): ...` subject (a release with no image-content change is harmless). Alternative: also allowlist `^\.(git|docker)ignore$`, which is not requested and is rejected here because `.dockerignore` does influence the build context.
- Exact pinned Rust toolchain version and `cargo-audit` version are not specified. Proposed: `channel = "1.85.0"` (oldest stable that reads lockfile v4 and is widely available on runners) with `clippy` and `rustfmt` components, and `cargo install cargo-audit --locked --version <latest 0.x at implementation time>`. The reviewer should confirm or substitute newer pins.
- The issue calls the workflow "optional". This proposal includes it, because the Definition of done requires it to run green on the PR.
