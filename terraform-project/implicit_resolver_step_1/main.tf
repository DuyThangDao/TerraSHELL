# --- LOCALS BLOCK (Lớp trung gian) ---
locals {
  # Case 1: Tham chiếu trực tiếp biến
  app_id = var.project_name

  # Case 2: Nội suy chuỗi (String Interpolation)
  # Logic: "phoenix" + "-" + "production" -> "phoenix-production"
  full_name_prefix = "${var.project_name}-${var.environment}"

  # Case 3: Nested Interpolation (Tham chiếu local trong local)
  # Logic: "phoenix-production" + "-logs" -> "phoenix-production-logs"
  bucket_name_template = "${local.full_name_prefix}-logs"
}

# --- RESOURCES (Nơi cần giải mã) ---

# TEST CASE A: Tham chiếu trực tiếp (Direct Reference)
# Mong đợi: bucket = "phoenix"
resource "aws_s3_bucket" "simple_ref" {
  bucket = var.project_name
}

# TEST CASE B: Nội suy chuỗi cơ bản (Basic Interpolation)
# Mong đợi: name = "queue-us1-high-priority"
# Test Regex: ${var.region_short_code} nằm giữa chuỗi
resource "aws_sqs_queue" "interp_ref" {
  name = "queue-${var.region_short_code}-high-priority"
}

# TEST CASE C: Xử lý khoảng trắng (Whitespace Handling)
# Mong đợi: name = "/config/production/db"
# Test Regex: ${  var.environment  } (có dấu cách)
resource "aws_ssm_parameter" "space_test" {
  name  = "/config/${  var.environment  }/db"
  type  = "String"
  value = "connection_string"
}

# TEST CASE D: Lan truyền qua Local (Variable -> Local -> Resource)
# Mong đợi: bucket = "phoenix-production-logs"
# Đây là case khó nhất: Python phải trace được var -> local -> resource
resource "aws_s3_bucket" "local_chain_ref" {
  bucket = local.bucket_name_template
}

# TEST CASE E: Trộn lẫn (Mix)
# Mong đợi: Tag "CostCenter" = "Billing-999"
resource "aws_instance" "mixed_ref" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"

  tags = {
    Name       = "Server-${var.project_name}"
    Env        = local.full_name_prefix
    CostCenter = "Billing-${var.billing_id}"
  }
}