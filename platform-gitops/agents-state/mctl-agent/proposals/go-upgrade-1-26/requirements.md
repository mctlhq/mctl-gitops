# Upgrade Go toolchain to 1.26.2

## Context
mctl-agent is built on Go 1.24. The Go 1.26.2 release (2026-04-07) contains security
fixes in `crypto/tls`, `crypto/x509`, `html/template`, and the `os` package. Every
outbound connection from the agent to the GitHub API and the Anthropic API goes through
TLS — vulnerabilities in crypto/tls directly affect the main operational path. The
current toolchain is two minor releases behind, accumulating CVE debt in the standard
library. Additionally, Go 1.26.0 enabled Green Tea GC by default, reducing GC overhead by
10–40% without an increase in memory consumption.

## User stories

- AS a platform engineer I WANT mctl-agent to be built with Go 1.26.2 SO THAT known
  security vulnerabilities in crypto/tls and crypto/x509 are remediated.
- AS a platform operator I WANT mctl-agent to benefit from Green Tea GC SO THAT GC
  latency spikes do not affect alert-processing throughput.

## Acceptance criteria (EARS)

- WHEN mctl-agent is built, THE SYSTEM SHALL use Go toolchain 1.26.2 or later.
- WHEN mctl-agent establishes a TLS connection to GitHub API or Anthropic API,
  THE SYSTEM SHALL use a runtime free of known CVEs in `crypto/tls` and `crypto/x509`.
- WHILE mctl-agent is running under load, THE SYSTEM SHALL exhibit GC overhead reduced
  by the Green Tea GC compared to Go 1.24 baseline (verifiable via `go tool pprof`).
- IF any existing unit or integration test fails after the toolchain bump,
  THE SYSTEM SHALL NOT be released until all tests pass.

## Out of scope

- Application code changes (toolchain only).
- Upgrade of third-party Go dependencies (chi, go-github etc.) — separate proposals.
- Changes to CRDs or GitOps manifests.
