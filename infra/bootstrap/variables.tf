# The GitHub repository whose workflows may assume the CI roles. It sends
# immutable OIDC subject claims, which include the numeric owner and repository
# IDs. This command prints the prefix the trust policies must match,
# repo:<owner>@<owner ID>/<repository>@<repository ID>:
#   gh api repos/ValentinCasanova/shipscope/actions/oidc/customization/sub

variable "github_owner" {
  description = "GitHub account that owns the repository."
  type        = string
  default     = "ValentinCasanova"
}

variable "github_owner_id" {
  description = "Numeric ID of the GitHub account that owns the repository."
  type        = string
  default     = "129884225"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must be a numeric GitHub account ID."
  }
}

variable "github_repository" {
  description = "Name of the GitHub repository, without the owner."
  type        = string
  default     = "shipscope"
}

variable "github_repository_id" {
  description = "Numeric ID of the GitHub repository."
  type        = string
  default     = "1368534118"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must be a numeric GitHub repository ID."
  }
}
