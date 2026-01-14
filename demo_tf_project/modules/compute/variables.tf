variable "service_name" {
  type = string # Tên biến khác với Root, tool phải tự map
}

variable "security_group_id" {
  type = string # Nhận kết quả từ module security
}