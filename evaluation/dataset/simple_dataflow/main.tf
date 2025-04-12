provider "aws" {
  region = "us-west-2"
}

# IAM Role for EC2 Instance
resource "aws_iam_role" "ec2_role" {
  name = "ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "ec2.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

# IAM Policy for EC2 Instance to Access S3 Bucket
resource "aws_iam_policy" "s3_access_policy" {
  name        = "s3_access_policy"
  description = "Allows EC2 instance to access S3 bucket"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      Resource = [
        aws_s3_bucket.example.arn,
        "${aws_s3_bucket.example.arn}/*"
      ]
    }]
  })
}

# Attach IAM Policy to IAM Role
resource "aws_iam_role_policy_attachment" "s3_access_attachment" {
  policy_arn = aws_iam_policy.s3_access_policy.arn
  role       = aws_iam_role.ec2_role.name
}

# AWS EC2 Instance
resource "aws_instance" "example" {
  ami                  = "ami-083abdc7ac7d736dd"
  instance_type        = "t2.micro"
  iam_instance_profile = aws_iam_role.ec2_role.name
  tags = {
    Name = "example-instance"
  }
}

# API Gateway
resource "aws_api_gateway_rest_api" "example" {
  name        = "example-api"
  description = "Example API Gateway"
}

resource "aws_api_gateway_resource" "example" {
  rest_api_id = aws_api_gateway_rest_api.example.id
  parent_id   = aws_api_gateway_rest_api.example.root_resource_id
  path_part   = "example"
}

resource "aws_api_gateway_method" "example" {
  rest_api_id   = aws_api_gateway_rest_api.example.id
  resource_id   = aws_api_gateway_resource.example.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "example" {
  rest_api_id             = aws_api_gateway_rest_api.example.id
  resource_id             = aws_api_gateway_resource.example.id
  http_method             = aws_api_gateway_method.example.http_method
  integration_http_method = "GET"
  type                    = "AWS_PROXY"
  uri                     = aws_instance.example.public_ip # Endpoint of EC2 instance
}

# Amazon S3
resource "aws_s3_bucket" "example" {
  bucket = "example-bucket-v2a13a"
}

# Connection from API Gateway to AWS EC2 Instance
resource "aws_api_gateway_integration_response" "example" {
  rest_api_id = aws_api_gateway_rest_api.example.id
  resource_id = aws_api_gateway_resource.example.id
  http_method = aws_api_gateway_method.example.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "example" {
  rest_api_id = aws_api_gateway_rest_api.example.id
  resource_id = aws_api_gateway_resource.example.id
  http_method = aws_api_gateway_method.example.http_method
  status_code = "200"
}
