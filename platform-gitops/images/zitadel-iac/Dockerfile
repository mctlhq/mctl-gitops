# syntax=docker/dockerfile:1
#
# Runtime for the in-cluster OpenTofu Job that applies the declarative ZITADEL
# configuration (mctlhq/mctl-gitops#1520).
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/zitadel-iac/Dockerfile
#   image_name=ghcr.io/mctlhq/zitadel-iac  image_tag=<tofu version>-<ZITADEL_PROVIDER_VERSION>-<KUBERNETES_PROVIDER_VERSION>
#
# The official OpenTofu image is meant to have its binary copied out, not to
# be run, so it is used only as a source here. The providers are baked
# in as a filesystem mirror and registry access is excluded at runtime: the
# Job then needs no egress beyond the ZITADEL API, and what it runs is exactly
# what this file pins. To bump OpenTofu, edit the tag AND digest on the FROM
# line below (an ARG cannot be checked against a digest, so there is none);
# bump a provider version together with the root's .terraform.lock.hcl.
#
# hashicorp/kubernetes writes the OIDC client credentials ZITADEL generates
# into the consuming application's namespace (#1520 S4), into one Secret that
# namespace pre-creates and grants this Job update on by name.

ARG ZITADEL_PROVIDER_VERSION=3.8.7
ARG KUBERNETES_PROVIDER_VERSION=3.3.0

FROM ghcr.io/opentofu/opentofu:1.13.1-minimal@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6 AS tofu

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS mirror
ARG ZITADEL_PROVIDER_VERSION
ARG KUBERNETES_PROVIDER_VERSION
# The base already carries ca-certificates-bundle; installing the package
# makes the TLS trust this stage's HTTPS download relies on explicit.
RUN apk add --no-cache ca-certificates
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
WORKDIR /mirror-src
RUN printf 'terraform {\n  required_providers {\n    zitadel = {\n      source  = "zitadel/zitadel"\n      version = "%s"\n    }\n    kubernetes = {\n      source  = "hashicorp/kubernetes"\n      version = "%s"\n    }\n  }\n}\n' "${ZITADEL_PROVIDER_VERSION}" "${KUBERNETES_PROVIDER_VERSION}" > versions.tf \
 && tofu providers mirror -platform=linux_amd64 /usr/share/tofu/providers \
 && test -n "$(find /usr/share/tofu/providers/registry.opentofu.org/zitadel -name '*.zip')" \
 && test -n "$(find /usr/share/tofu/providers/registry.opentofu.org/hashicorp -name '*.zip')"

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
ARG ZITADEL_PROVIDER_VERSION
ARG KUBERNETES_PROVIDER_VERSION
LABEL org.opencontainers.image.title="zitadel-iac" \
      org.opencontainers.image.description="OpenTofu with the zitadel ${ZITADEL_PROVIDER_VERSION} and kubernetes ${KUBERNETES_PROVIDER_VERSION} providers pre-installed" \
      org.opencontainers.image.source="https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/images/zitadel-iac" \
      org.opencontainers.image.licenses="MPL-2.0"
RUN apk add --no-cache ca-certificates
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
COPY --from=mirror /usr/share/tofu/providers /usr/share/tofu/providers
COPY --from=mirror /mirror-src/versions.tf /usr/share/tofu/versions.tf
# Only the mirror, no `direct` block: with no direct method there is no
# network installation at all, whatever hostname a source names. (A pattern
# like "*/*" would only cover the default registry host.)
RUN printf 'provider_installation {\n  filesystem_mirror {\n    path = "/usr/share/tofu/providers"\n  }\n}\n' > /etc/tofurc \
 && tofu version
ENV TF_CLI_CONFIG_FILE=/etc/tofurc \
    TF_IN_AUTOMATION=1 \
    TF_INPUT=0
# The image is only correct if init works with no network at all: prove it at
# build time, so an image whose mirror does not resolve is never published.
RUN --network=none mkdir /tmp/offline-check && cd /tmp/offline-check \
 && cp /usr/share/tofu/versions.tf . \
 && tofu init -backend=false \
 && tofu providers | grep -q "zitadel/zitadel\] ${ZITADEL_PROVIDER_VERSION}" \
 && tofu providers | grep -q "hashicorp/kubernetes\] ${KUBERNETES_PROVIDER_VERSION}" \
 && cd / && rm -rf /tmp/offline-check
# Non-root, with a writable HOME for tofu's plugin cache and .terraform.d.
RUN adduser -D -u 65532 -h /home/tofu tofu
USER 65532
WORKDIR /home/tofu
ENTRYPOINT ["/usr/local/bin/tofu"]
