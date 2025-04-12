provider "aws" {
  region = "us-west-2" # Change this to your desired AWS region
}

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}