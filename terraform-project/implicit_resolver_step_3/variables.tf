variable "region" {
  default = "us-east-1"
}

variable "db_host_name" {
  description = "Tên DB thực tế"
  default     = "payment-db-production"
}

variable "queue_prefix" {
  default = "order-events"
}