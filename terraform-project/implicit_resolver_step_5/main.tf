# ==========================================
# INTERNAL RESOURCES (Để hệ thống không nhầm lẫn)
# ==========================================
resource "aws_s3_bucket" "local_bucket" {
  bucket = "my-local-bucket"
}

# ==========================================
# RESOURCES TRỎ RA NGOÀI (Ghost Candidates)
# ==========================================

# 1. Lambda kết nối Payment Gateway & Auth0
resource "aws_lambda_function" "backend_api" {
  function_name = "backend-api"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # Step 1 sẽ giải mã biến này thành URL Stripe
      # Step 5 sẽ bắt URL này và tạo Ghost Node
      STRIPE_ENDPOINT = var.payment_gateway_url
      
      # Step 1 giải mã thành domain Auth0
      AUTH_DOMAIN     = var.auth0_domain
    }
  }
}

# 2. Security Group Rule cho Legacy DB IP
resource "aws_security_group_rule" "allow_legacy_db" {
  type        = "egress"
  from_port   = 3306
  to_port     = 3306
  protocol    = "tcp"
  
  # Step 5 sẽ quét description và bắt được IP
  description = "Connect to Legacy MySQL at ${var.legacy_db_ip}"
  security_group_id = "sg-12345"
}

# 3. IAM Policy cho Partner Bucket ARN
resource "aws_iam_policy" "partner_access" {
  name        = "partner-access-policy"
  description = "Allow access to ${var.partner_bucket_arn}"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["s3:GetObject"]
        Effect   = "Allow"
        # Step 5 sẽ bắt được ARN này trong policy string
        Resource = var.partner_bucket_arn
      }
    ]
  })
}