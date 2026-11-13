# Neon (Postgres) and Vercel (web app), both on their free plans. The API runs as a Docker
# Space on Hugging Face, deployed by .github/workflows/deploy-api.yml, not by Terraform.
# State stays local (git-ignored). Tokens are read from the environment:
#   NEON_API_KEY      Neon API key
#   VERCEL_API_TOKEN  Vercel token
terraform {
  required_version = ">= 1.6"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.18"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 3.17"
    }
  }
}

provider "neon" {}

provider "vercel" {
  team = var.vercel_team
}
