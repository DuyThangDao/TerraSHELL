# ==========================================
# TARGET RESOURCES (Tên chuẩn)
# ==========================================

# 1. Database (RDS)
resource "aws_db_instance" "payment_db" {
  # Physical ID: payment-db-production
  identifier = "payment-db-${var.env}" 
}

# 2. Storage (S3)
resource "aws_s3_bucket" "data_lake" {
  # Physical ID: data-lake-logs
  bucket = "data-lake-logs"
}

# 3. Compute (EC2)
resource "aws_instance" "auth_server" {
  tags = {
    # Physical ID: auth-service
    Name = "auth-service"
  }
}

# ==========================================
# SOURCE RESOURCE (Chứa biến lỗi)
# ==========================================

resource "aws_lambda_function" "app_connector" {
  function_name = "app-connector"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # CASE A: Typo + Step 1 Dependency
      # Logic: 
      # 1. Step 1 giải mã var.db_identifier_typo -> "payment-db-prodution"
      # 2. Step 2 so sánh "payment-db-prodution" vs "payment-db-production" -> KHÁC -> Bỏ qua.
      # 3. Step 4 thấy property tên "DB_HOST" -> Tìm trong danh sách DB.
      # 4. Fuzzy Match (98%) -> TẠO LINK.
      DB_HOST = var.db_identifier_typo

      # CASE B: Naming Convention
      # Logic:
      # 1. Step 1 giải mã -> "data_lake_logs"
      # 2. Step 4 thấy property "TARGET_BUCKET" -> Tìm trong S3.
      # 3. So sánh "data_lake_logs" vs "data-lake-logs" -> TẠO LINK.
      TARGET_BUCKET = var.bucket_name_variant

      # CASE C: Type Filtering Safety
      # Giả sử có 1 cái S3 bucket cũng tên là "auth-service".
      # Nhưng biến này tên là "AUTH_HOST".
      # Step 4 sẽ CHỈ tìm trong EC2/DB, KHÔNG nối nhầm sang S3.
      AUTH_HOST = var.host_name_typo
    }
  }
}