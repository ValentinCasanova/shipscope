variable "backend_image" {
  description = "Backend image by digest. Releases pass the image they built; for a local plan, pass the one running now: -var \"backend_image=$(infra/scripts/deployed-image.sh staging)\"."
  type        = string
}
