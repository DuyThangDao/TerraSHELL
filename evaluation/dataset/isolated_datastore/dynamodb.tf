resource "aws_dynamodb_table" "dynamodb_table" {
  name         = "example-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "Id"
  attribute {
    name = "Id"
    type = "S"
  }
}