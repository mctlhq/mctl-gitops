path "secret/data/preprod/*" {
  capabilities = ["read"]
}

path "secret/metadata/preprod/*" {
  capabilities = ["read", "list"]
}
