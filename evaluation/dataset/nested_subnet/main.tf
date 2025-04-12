provider "aws" {
  region = "us-west-2"
}

# VPC, Subnet, and Security Groups
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "subnet" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
}

resource "aws_security_group" "lb_sg" {
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ec2_sg" {
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# DynamoDB Table
resource "aws_dynamodb_table" "example" {
  name         = "example-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Name = "example-table"
  }
}

# ElastiCache Cluster
resource "aws_elasticache_subnet_group" "example" {
  name       = "example"
  subnet_ids = [aws_subnet.subnet.id]
}

resource "aws_elasticache_cluster" "example" {
  cluster_id           = "example"
  engine               = "redis"
  node_type            = "cache.t2.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis3.2"
  subnet_group_name    = aws_elasticache_subnet_group.example.name
  security_group_ids   = [aws_security_group.ec2_sg.id]
}

# EC2 Instances
resource "aws_instance" "ec2_instance1" {
  ami             = "ami-0c55b159cbfafe1f0" # Update with the latest Amazon Linux AMI
  instance_type   = "t2.micro"
  subnet_id       = aws_subnet.subnet.id
  security_groups = [aws_security_group.ec2_sg.name]

  iam_instance_profile = aws_iam_instance_profile.ec2_instance_profile.name

  tags = {
    Name = "EC2Instance1"
  }
}

resource "aws_instance" "ec2_instance2" {
  ami             = "ami-0c55b159cbfafe1f0" # Update with the latest Amazon Linux AMI
  instance_type   = "t2.micro"
  subnet_id       = aws_subnet.subnet.id
  security_groups = [aws_security_group.ec2_sg.name]

  iam_instance_profile = aws_iam_instance_profile.ec2_instance_profile.name

  tags = {
    Name = "EC2Instance2"
  }
}

# Load Balancer
resource "aws_lb" "main" {
  name               = "main-lb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb_sg.id]
  subnets            = [aws_subnet.subnet.id]

  enable_deletion_protection = false

  tags = {
    Name = "main-lb"
  }
}

# Load Balancer Target Group
resource "aws_lb_target_group" "main" {
  name     = "main-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
    matcher             = "200"
  }
}

# Load Balancer Listener
resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}

# Register EC2 Instances with Target Group
resource "aws_lb_target_group_attachment" "ec2_instance1" {
  target_group_arn = aws_lb_target_group.main.arn
  target_id        = aws_instance.ec2_instance1.id
  port             = 80
}

resource "aws_lb_target_group_attachment" "ec2_instance2" {
  target_group_arn = aws_lb_target_group.main.arn
  target_id        = aws_instance.ec2_instance2.id
  port             = 80
}

# IAM Role and Policies for EC2
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_role" {
  name               = "ec2_role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_policy" "ec2_policy" {
  name        = "ec2_policy"
  description = "IAM policy for EC2 to access DynamoDB and ElastiCache"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "dynamodb:*",
          "elasticache:*",
          "logs:*",
          "cloudwatch:*",
        ]
        Effect   = "Allow"
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_policy_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_policy.arn
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "ec2_instance_profile"
  role = aws_iam_role.ec2_role.name
}

data "aws_availability_zones" "available" {}
