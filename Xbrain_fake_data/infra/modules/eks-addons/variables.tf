variable "argocd_name" {
  type        = string
  description = "Name of the ArgoCD Helm release"
  default     = "argocd"
}

variable "argocd_repository" {
  type        = string
  description = "Helm repository for ArgoCD"
  default     = "https://argoproj.github.io/argo-helm"
}

variable "argocd_chart" {
  type        = string
  description = "Helm chart name for ArgoCD"
  default     = "argo-cd"
}

variable "argocd_namespace" {
  type        = string
  description = "Namespace to install ArgoCD"
  default     = "argocd"
}

variable "argocd_version" {
  type        = string
  description = "Version of the ArgoCD Helm chart"
  default     = "7.0.0"
}

variable "create_argocd_namespace" {
  type        = bool
  description = "Whether to create the namespace for ArgoCD"
  default     = true
}
