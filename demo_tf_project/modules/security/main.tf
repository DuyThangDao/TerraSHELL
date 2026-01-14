resource "aws_security_group" "web_sg" {
  # Sink 1: Giá trị "unicorn-app-2026" chui vào đây
  name        = "${var.app_label}-sg" 
  description = "Allow HTTP traffic for ${var.app_label}"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}