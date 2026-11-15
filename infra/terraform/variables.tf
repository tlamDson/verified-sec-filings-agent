variable "neon_project_name" {
  description = "Name of the Neon project."
  type        = string
  default     = "sec-agent"
}

variable "neon_org_id" {
  description = "Neon organization that owns the project (null: the key's default)."
  type        = string
  default     = null
}

variable "neon_region" {
  description = "Neon region, near the Hugging Face Space and Vercel's default (iad1)."
  type        = string
  default     = "aws-us-east-1"
}

variable "vercel_team" {
  description = "Vercel team slug or id (null: the token's personal account)."
  type        = string
  default     = null
}

variable "vercel_project_name" {
  description = "Name of the Vercel project; the site is https://<name>.vercel.app."
  type        = string
  default     = "sec-agent"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) Vercel builds from; null leaves it unlinked."
  type        = string
  default     = null
}

variable "web_url" {
  description = "Public URL of the web app for Auth.js (null: https://<project>.vercel.app)."
  type        = string
  default     = null
}

variable "hf_space" {
  description = "Hugging Face Space that serves the API, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$", var.hf_space))
    error_message = "hf_space must look like owner/name."
  }
}

variable "api_auth_secret" {
  description = "Shared secret the web app signs API calls with (same value on the Space)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.api_auth_secret) >= 32 && !startswith(var.api_auth_secret, "change-me")
    error_message = "api_auth_secret needs 32 or more characters and must not be the placeholder."
  }
}

variable "nextauth_secret" {
  description = "Secret Auth.js signs the session cookie with."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.nextauth_secret) >= 32 && !startswith(var.nextauth_secret, "change-me")
    error_message = "nextauth_secret needs 32 or more characters and must not be the placeholder."
  }
}

variable "auth_github_id" {
  description = "GitHub OAuth app client id (empty: no GitHub sign-in)."
  type        = string
  default     = ""
}

variable "auth_github_secret" {
  description = "GitHub OAuth app client secret."
  type        = string
  default     = ""
  sensitive   = true
}
