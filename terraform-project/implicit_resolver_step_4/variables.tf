variable "env" {
  description = "Môi trường hiện tại"
  default     = "production"
}

# SCENARIO 1: Lỗi chính tả (Typo)
# Target thật: "payment-db-production"
# Giá trị nhập vào: thiếu chữ 'c' trong production
variable "db_identifier_typo" {
  default = "payment-db-prodution" 
}

# SCENARIO 2: Sai quy ước (Snake_case vs Kebab-case)
# Target thật: "data-lake-logs" (gạch ngang)
# Giá trị nhập vào: dùng gạch dưới
variable "bucket_name_variant" {
  default = "data_lake_logs"
}

# SCENARIO 3: Biến cho Type Filtering
# Target thật: "auth-service" (EC2)
# Giá trị nhập vào: "auth-servce" (Typo nhẹ)
variable "host_name_typo" {
  default = "auth-servce"
}