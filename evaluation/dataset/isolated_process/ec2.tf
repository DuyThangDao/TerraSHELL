variable "ami" {
  default = "ami-083abdc7ac7d736dd"
}

variable "instance_type" {
  default = "t2.micro"
}

resource "aws_instance" "ec2_instance" {
  ami           = var.ami
  instance_type = var.instance_type
  tags = {
    Name = "EC2 Instance"
  }
}