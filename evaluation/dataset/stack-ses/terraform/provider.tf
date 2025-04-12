provider "aws" {
  access_key = var.access_key
  secret_key = var.secret_key
  region     = var.aws_region
  version    = "~> 2.32"
}

# required to allow to toggle aws access keys
# based on issue here: https://github.com/hashicorp/terraform-provider-aws/issues/23180
provider "toggles" {}
