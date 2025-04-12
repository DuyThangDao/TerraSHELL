resource "aws_db_instance" "example_rds_instance" {
  allocated_storage = 10
  engine            = "mysql"
  instance_class    = "db.t3.micro"
  username          = "admin"
  password          = "Password123"
  skip_final_snapshot = true
}