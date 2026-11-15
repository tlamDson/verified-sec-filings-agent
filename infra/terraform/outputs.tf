output "database_url" {
  description = "Connection string of the Neon database; store it as the GitHub secret DATABASE_URL."
  value       = neon_project.main.connection_uri
  sensitive   = true
}

output "api_base_url" {
  description = "Where the web app reaches the API (the Hugging Face Space)."
  value       = local.api_base_url
}

output "web_url" {
  description = "Public URL of the web app."
  value       = local.web_url
}
