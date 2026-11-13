locals {
  # A Space owner/name is served at https://<owner>-<name>.hf.space, lower case, with every
  # character other than a letter or digit turned into "-".
  api_base_url = "https://${replace(lower(var.hf_space), "/[^a-z0-9]+/", "-")}.hf.space"
  web_url      = coalesce(var.web_url, "https://${var.vercel_project_name}.vercel.app")
  targets      = ["production", "preview"]
}

# The Next.js app in web/ of the pnpm workspace, on the Hobby plan.
resource "vercel_project" "web" {
  name           = var.vercel_project_name
  framework      = "nextjs"
  root_directory = "web"

  git_repository = var.github_repo == null ? null : {
    type              = "github"
    repo              = var.github_repo
    production_branch = "main"
  }
}

resource "vercel_project_environment_variable" "api_base_url" {
  project_id = vercel_project.web.id
  key        = "API_BASE_URL"
  value      = local.api_base_url
  target     = local.targets
}

resource "vercel_project_environment_variable" "nextauth_url" {
  project_id = vercel_project.web.id
  key        = "NEXTAUTH_URL"
  value      = local.web_url
  target     = local.targets
}

resource "vercel_project_environment_variable" "api_auth_secret" {
  project_id = vercel_project.web.id
  key        = "API_AUTH_SECRET"
  value      = var.api_auth_secret
  target     = local.targets
  sensitive  = true
}

resource "vercel_project_environment_variable" "nextauth_secret" {
  project_id = vercel_project.web.id
  key        = "NEXTAUTH_SECRET"
  value      = var.nextauth_secret
  target     = local.targets
  sensitive  = true
}

resource "vercel_project_environment_variable" "auth_github_id" {
  count      = var.auth_github_id == "" ? 0 : 1
  project_id = vercel_project.web.id
  key        = "AUTH_GITHUB_ID"
  value      = var.auth_github_id
  target     = local.targets
}

resource "vercel_project_environment_variable" "auth_github_secret" {
  count      = var.auth_github_id == "" ? 0 : 1
  project_id = vercel_project.web.id
  key        = "AUTH_GITHUB_SECRET"
  value      = var.auth_github_secret
  target     = local.targets
  sensitive  = true
}
