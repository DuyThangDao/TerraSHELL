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

# --- TARGET: S3 bucket (sẽ được Lambda tham chiếu ngầm) ---
# Physical ID: "app-data-bucket" → Step 2 index vào symbol table
# Logical: aws_s3_bucket.data_bucket / base: data_bucket
resource "aws_s3_bucket" "data_bucket" {
  # bucket = "app-data-bucket"
  bucket = var.bucket_name
}

# --- SOURCE: Lambda có tham chiếu ngầm tới S3 (test Step 2 Exact Matching) ---
# Không dùng aws_s3_bucket.data_bucket.id → graph không có REF Lambda → S3
# Step 2: extract_string_values lấy "app-data-bucket" → match symbol table → tạo REF
resource "aws_lambda_function" "processor" {
  function_name = "test-processor"
  role          = "arn:aws:iam::123456789012:role/dummy"
  handler       = "index.handler"
  runtime       = "python3.9"

  # Implicit reference: hardcoded bucket name thay vì aws_s3_bucket.data_bucket.id
  environment {
    variables = {
      # BUCKET_NAME = "app-data-bucket"
      # BUCKET_NAME = aws_s3_bucket.data_bucket.bucket
      BUCKET_NAME = var.bucket_name
    }
  }
}
