provider "aws" {
  region = "us-east-1"
}

# Gọi Module Security
module "firewall_stack" {
  source = "./modules/security"

  # Truyền biến: Tên biến đổi từ 'global_project_name' thành 'app_label'
  app_label   = var.global_project_name 
  environment = var.env
}

# Gọi Module Compute
module "web_server_stack" {
  source = "./modules/compute"

  # Truyền biến: Tên biến đổi từ 'global_project_name' thành 'service_name'
  service_name = var.global_project_name
  
  # Truyền Dependency: Lấy output từ module firewall đút vào module compute
  # Đây là phép thử cho việc lan truyền ID giữa các module
  security_group_id = module.firewall_stack.sg_id
}