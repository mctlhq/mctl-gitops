terraform {
  backend "s3" {
    endpoints = {
      s3 = "https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com"
    }
    bucket                      = "mctl-terraform-state"
    key                         = "k3s-preview/terraform.tfstate"
    region                      = "auto"
    use_lockfile                = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    use_path_style              = true
  }
}
