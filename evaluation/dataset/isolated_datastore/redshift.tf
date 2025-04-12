resource "aws_redshift_cluster" "redshift_cluster" {
  cluster_identifier  = "example-cluster"
  node_type           = "dc2.large"
  cluster_type        = "single-node"
  master_username     = "admin"
  master_password     = "Password123"
  skip_final_snapshot = true
}