variable "env" {
  description = "Môi trường"
  default     = "production"
}

variable "project_code" {
  description = "Mã dự án"
  default     = "alpha"
}

# Biến này chứa TÊN THẬT (Physical ID) của Queue
variable "target_queue_name" {
  description = "Tên Queue cần kết nối"
  default     = "order-processing-queue-production"
}