output "deploy_sa_email" {
  value = google_service_account.deploy.email
}

output "runtime_sa_email" {
  value = google_service_account.runtime.email
}

output "runtime_sa_member" {
  value = google_service_account.runtime.member
}

output "dashboard_sa_email" {
  value = google_service_account.dashboard.email
}
