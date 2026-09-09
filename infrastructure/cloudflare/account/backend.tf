terraform {
  backend "s3" {
    endpoints = {
      s3 = "https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com"
    }
    bucket = "mctl-terraform-state"
    key    = "cloudflare/account/terraform.tfstate"
    region = "auto"

    # Native S3 conditional-write locking. R2 supports it; there is no
    # DynamoDB-style lock table involved.
    use_lockfile = true

    # R2 is S3-compatible but not AWS: these checks would otherwise try to
    # reach AWS endpoints that do not exist here.
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    use_path_style              = true
  }
}
