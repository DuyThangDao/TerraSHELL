resource "aws_instance" "app_server" {
  ami           = "ami-0c55b159cbfafe1f0" # Ubuntu example
  instance_type = "t2.micro"

  # Sink 2: Giá trị "unicorn-app-2026" chui vào Tags
  tags = {
    Name    = "server-${var.service_name}"
    Project = var.service_name
  }

  # Dependency Sink: Security Group ID (được tạo ở module kia) chui vào đây
  vpc_security_group_ids = [var.security_group_id]
}