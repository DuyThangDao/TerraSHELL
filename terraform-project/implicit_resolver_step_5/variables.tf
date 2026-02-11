# CASE 1: External URL (SaaS)
variable "payment_gateway_url" {
  description = "URL của cổng thanh toán Stripe"
  default     = "https://api.stripe.com/v1/charges"
}

# CASE 2: Legacy IP (On-premise Database)
variable "legacy_db_ip" {
  description = "IP của database cũ chạy máy vật lý"
  default     = "192.168.10.55"
}

# CASE 3: Cross-Account ARN (Partner S3)
variable "partner_bucket_arn" {
  description = "ARN bucket của đối tác (không nằm trong code này)"
  default     = "arn:aws:s3:::partner-data-sync-prod"
}

# CASE 4: External Domain (Auth Provider)
variable "auth0_domain" {
  description = "Domain xác thực Auth0"
  default     = "my-app.auth0.com"
}