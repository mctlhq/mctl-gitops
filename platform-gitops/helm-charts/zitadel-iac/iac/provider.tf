# Authenticates as the System API user `iac`, declared in ZITADEL's runtime
# config (SystemAPIUsers in bootstrap/templates/core-infra/zitadel.yaml) by the
# public half of the cert-manager key pair zitadel-iac-key. No console-created
# credential exists, and the private key never leaves the zitadel namespace.
#
# The API is reached in-cluster, but ZITADEL picks the instance from the host:
# without the instance-host header a request resolves no instance and an
# import reports "non-existent remote object" instead of an auth error
# (measured on v4.19.2). The JWT audience is the public issuer for the same
# reason.
provider "zitadel" {
  domain   = "zitadel.zitadel.svc.cluster.local"
  port     = "8080"
  insecure = true

  transport_headers = {
    "x-zitadel-instance-host" = "auth.mctl.ai"
  }

  system_api {
    user     = "iac"
    key_file = "/iac-key/tls.key"
    audience = "https://auth.mctl.ai"
  }
}
