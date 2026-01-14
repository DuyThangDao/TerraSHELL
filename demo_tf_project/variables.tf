variable "global_project_name" {
  description = "Tên dự án chung, giá trị này sẽ lan truyền khắp nơi"
  type        = string
  default     = "unicorn-app-2026"  # <--- HÃY THEO DÕI GIÁ TRỊ NÀY
}

variable "env" {
  default = "production"
}