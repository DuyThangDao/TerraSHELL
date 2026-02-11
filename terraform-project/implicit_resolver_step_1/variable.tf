variable "project_name" {
  description = "Tên dự án"
  type        = string
  default     = "phoenix"
}

variable "environment" {
  description = "Môi trường triển khai"
  type        = string
  default     = "production"
}

variable "region_short_code" {
  description = "Mã vùng ngắn gọn"
  type        = string
  default     = "us1"
}

variable "billing_id" {
  description = "ID thanh toán (Test case số nguyên)"
  type        = string # Terraform tự convert int sang string trong template
  default     = "999"
}