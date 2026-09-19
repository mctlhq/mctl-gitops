terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # Backend declared in backend.tf.
}

# Credentials come from CLOUDFLARE_API_TOKEN in the environment — never from a
# .tf or .tfvars file.
provider "cloudflare" {}
