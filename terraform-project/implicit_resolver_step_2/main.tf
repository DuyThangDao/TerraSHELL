terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region = "ap-southeast-1"
}
# ============================================================================
# TEST PROJECT FOR STEP 2: EXACT MATCHING
# ============================================================================
# Mục đích: Kiểm tra độ chính xác của Step 2 (Exact Matching)
# 
# Test Cases bao gồm:
# - Positive cases: Should MATCH (✓)
# - Negative cases: Should NOT MATCH (✗) - False positive prevention
# - Edge cases: Self-reference, empty strings, nested structures
# ============================================================================

# ============================================================================
# RESOURCE ĐÍCH (TARGET RESOURCES) - Các resource sẽ được tham chiếu đến
# ============================================================================

# --- RESOURCE ĐÍCH 1: SQS QUEUE ---
# Physical ID: "order-processing-queue-production"
# (Được ghép từ biến, Step 1 phải giải mã được cái tên này thì Step 2 mới index được)
resource "aws_sqs_queue" "order_queue" {
  name = "order-processing-queue-${var.env}"
}

# --- RESOURCE ĐÍCH 2: S3 BUCKET ---
# Physical ID: "alpha-data-storage"
# Logical ID: "aws_s3_bucket.data_bucket"
resource "aws_s3_bucket" "data_bucket" {
  bucket = "${var.project_code}-data-storage"
}

# --- RESOURCE ĐÍCH 3: SECURITY GROUP (Test Case 4) ---
# Physical ID: "web-sg"
# Logical ID: "aws_security_group.web_sg"
resource "aws_security_group" "web_sg" {
  name = "web-sg"
  description = "Security group for web servers"
}

# --- RESOURCE ĐÍCH 4: SUBNET (Test Case 5) ---
# Physical ID: "private-subnet" (from tags.Name)
# Logical ID: "aws_subnet.private_subnet"
resource "aws_subnet" "private_subnet" {
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "private-subnet"
  }
}

# --- RESOURCE ĐÍCH 5: MULTIPLE SECURITY GROUPS (Test Case 6) ---
resource "aws_security_group" "sg1" {
  name = "web-sg"
}

resource "aws_security_group" "sg2" {
  name = "web-sg-alt"
}

# --- RESOURCE ĐÍCH 6: RDS INSTANCE (Test Case 7) ---
# Logical ID: "aws_db_instance.payment_db"
resource "aws_db_instance" "payment_db" {
  identifier = "payment-db"
  engine      = "postgres"
}

# ============================================================================
# RESOURCE NGUỒN (SOURCE RESOURCES) - Các resource chứa tham chiếu ẩn
# ============================================================================

# --- RESOURCE NGUỒN 1: LAMBDA FUNCTION (Test Cases 1-3) ---
# Đây là nơi chứa các tham chiếu ẩn (Implicit References)
resource "aws_lambda_function" "processor" {
  function_name = "event-processor"
  role          = "arn:aws:iam::123:role/dummy" # Step 2 sẽ bỏ qua ARN này (dành cho Step 3)

  environment {
    variables = {
      # TEST CASE 1: Step 1 + Enriched Step 2
      # Logic: 
      # 1. Step 1 giải mã "var.target_queue_name" -> "order-processing-queue-production"
      # 2. Step 2 Enriched tra bảng thấy "order-processing-queue-production" thuộc về "aws_sqs_queue.order_queue"
      # -> KẾT QUẢ: Tạo Link (Lambda -> SQS)
      # EXPECTED: ✓ MATCH
      QUEUE_TARGET = var.target_queue_name

      # TEST CASE 2: Step 1 + Logical ID Match
      # Logic:
      # 1. Step 1 giải mã -> "data_bucket" (Tên base logical)
      # 2. Step 2 tra bảng thấy "data_bucket" thuộc về "aws_s3_bucket.data_bucket"
      # -> KẾT QUẢ: Tạo Link (Lambda -> S3)
      # EXPECTED: ✓ MATCH
      BUCKET_LOGICAL_REF = "data_bucket"

      # TEST CASE 3: Hardcoded Physical ID (Enriched Step 2 Only)
      # Logic:
      # 1. Step 1 giải mã "${var.project_code}-data-storage" -> "alpha-data-storage"
      # 2. Step 2 Enriched tra bảng thấy "alpha-data-storage" thuộc về "aws_s3_bucket.data_bucket"
      # -> KẾT QUẢ: Tạo Link (Lambda -> S3)
      # EXPECTED: ✓ MATCH
      DIRECT_PHYSICAL_REF = "${var.project_code}-data-storage"
    }
  }
}

# --- RESOURCE NGUỒN 2: EC2 INSTANCE (Test Case 4) ---
# Test Case: EC2 → Security Group (hardcoded name)
resource "aws_instance" "web_server" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
  
  # TEST CASE 4: Hardcoded Security Group Name
  # Logic: Hardcoded string "web-sg" matches Security Group name
  # EXPECTED: ✓ MATCH (EC2 -> Security Group)
  vpc_security_group_ids = ["web-sg"]
}

# --- RESOURCE NGUỒN 3: RDS INSTANCE (Test Case 5) ---
# Test Case: RDS → Subnet (hardcoded subnet name)
resource "aws_db_instance" "app_db" {
  identifier = "app-database"
  engine      = "postgres"
  
  # TEST CASE 5: Hardcoded Subnet Name
  # Logic: Hardcoded string "private-subnet" matches Subnet tag Name
  # EXPECTED: ✓ MATCH (RDS -> Subnet)
  # NOTE: Step 2 should match against tags.Name if available
  subnet_id = "private-subnet"
}

# --- RESOURCE NGUỒN 4: EC2 WITH MULTIPLE SGs (Test Case 6) ---
# Test Case: Multiple matches
resource "aws_instance" "multi_sg_server" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
  
  # TEST CASE 6: Multiple Security Groups
  # Logic: Both "web-sg" and "web-sg-alt" should match
  # EXPECTED: ✓ MATCH (EC2 -> sg1) and ✓ MATCH (EC2 -> sg2)
  vpc_security_group_ids = ["web-sg", "web-sg-alt"]
}

# --- RESOURCE NGUỒN 5: LAMBDA WITH FALSE POSITIVES (Test Cases 7-12) ---
# Test Cases: Should NOT match (filtered out)
resource "aws_lambda_function" "filter_test" {
  function_name = "filter-test"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # TEST CASE 7: ARN should be FILTERED OUT (Step 3 handles this)
      # EXPECTED: ✗ NO MATCH (filtered by extract_string_values)
      DB_ARN = "arn:aws:rds:us-east-1:123456789012:db:payment-db"
      
      # TEST CASE 8: URL should be FILTERED OUT (Step 3 handles this)
      # EXPECTED: ✗ NO MATCH (filtered by extract_string_values)
      API_URL = "https://api.example.com/v1/endpoint"
      
      # TEST CASE 9: Empty string should be FILTERED OUT
      # EXPECTED: ✗ NO MATCH (filtered by is_identifier_string)
      EMPTY_REF = ""
      
      # TEST CASE 10: IP address should be FILTERED OUT
      # EXPECTED: ✗ NO MATCH (filtered by is_identifier_string)
      DB_HOST = "192.168.1.100"
      
      # TEST CASE 11: Email should be FILTERED OUT
      # EXPECTED: ✗ NO MATCH (filtered by is_identifier_string)
      ADMIN_EMAIL = "admin@example.com"
      
      # TEST CASE 12: Very long string should be FILTERED OUT
      # EXPECTED: ✗ NO MATCH (filtered by is_identifier_string, len > 100)
      LONG_STRING = "this-is-a-very-long-string-that-exceeds-one-hundred-characters-and-should-be-filtered-out-by-step-two-exact-matching"
    }
  }
}

# --- RESOURCE NGUỒN 6: CASE SENSITIVITY TEST (Test Cases 13-14) ---
resource "aws_lambda_function" "case_test" {
  function_name = "case-test"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # TEST CASE 13: Case-insensitive match (default)
      # If case_sensitive=False: Should match "payment-db" with "payment_db" (base name)
      # EXPECTED: ✓ MATCH (case-insensitive)
      DB_NAME_LOWER = "payment-db"
      
      # TEST CASE 14: Case variation
      # EXPECTED: ✓ MATCH (case-insensitive) or ✗ NO MATCH (case-sensitive)
      DB_NAME_UPPER = "PAYMENT-DB"
    }
  }
}

# --- RESOURCE NGUỒN 7: SELF-REFERENCE TEST (Test Case 15) ---
# Test Case: Should NOT create self-loop
resource "aws_lambda_function" "self_ref_test" {
  function_name = "self-ref-test"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # TEST CASE 15: Self-reference prevention
      # Logic: Lambda references its own function_name
      # EXPECTED: ✗ NO MATCH (self-loop prevention in create_implicit_links)
      FUNCTION_NAME = "self-ref-test"
    }
  }
}

# --- RESOURCE NGUỒN 8: NESTED STRUCTURE TEST (Test Case 16) ---
# Test Case: String in nested dict/list
resource "aws_lambda_function" "nested_test" {
  function_name = "nested-test"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # TEST CASE 16: Nested structure
      # Logic: String "payment-db" is nested in JSON object
      # EXPECTED: ✓ MATCH (extract_recursive should handle nested structures)
      config = jsonencode({
        database = {
          host = "payment-db"
          port = 5432
        }
        queues = [
          "order-processing-queue-production",  # Should match order_queue
          "alpha-data-storage"                   # Should match data_bucket
        ]
      })
    }
  }
}
