resource "helm_release" "argocd" {
  name             = var.argocd_name
  repository       = var.argocd_repository
  chart            = var.argocd_chart
  namespace        = var.argocd_namespace
  create_namespace = var.create_argocd_namespace
  version          = var.argocd_version
}
