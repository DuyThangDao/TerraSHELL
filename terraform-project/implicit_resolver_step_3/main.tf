# ==========================================
# TARGET RESOURCES (Đích đến)
# ==========================================

# TARGET 1: Database (RDS)
# Physical ID: "payment-db-production" (Lấy từ biến var.db_host_name)
resource "aws_db_instance" "main_db" {
  identifier = var.db_host_name
  engine     = "mysql"
}

# TARGET 2: SQS Queue
# Physical ID: "order-events-queue"
resource "aws_sqs_queue" "orders" {
  name = "${var.queue_prefix}-queue"
}

# TARGET 3: Resource có tên ngắn (Bẫy Boundary)
# Physical ID: "user"
# Logical ID: "aws_iam_user.user"
resource "aws_iam_user" "user" {
  name = "user"
}

# ==========================================
# SOURCE RESOURCE (Nơi chứa tham chiếu phức tạp)
# ==========================================

resource "aws_lambda_function" "api_handler" {
  function_name = "api-handler"
  role          = "arn:aws:iam::123:role/dummy"

  environment {
    variables = {
      # CASE A: ARN Hardcoded (Step 3 thuần túy)
      # Logic: Tìm "order-events-queue" trong chuỗi ARN dài ngoằng.
      # Step 1 giải mã ${var.queue_prefix} -> "order-events"
      # Chuỗi kết quả: "arn:aws:sqs:us-east-1:123456789:order-events-queue"
      # Step 3 Check: "order-events-queue" nằm cuối ARN, sau dấu hai chấm (:).
      # -> KẾT QUẢ MONG ĐỢI: MATCH ✅
      SQS_ARN = "arn:aws:sqs:${var.region}:123456789:order-events-queue"

      # CASE B: Connection String (Kết hợp Step 1 + Step 3)
      # Logic: 
      # 1. Step 1 giải mã ${var.db_host_name} -> "payment-db-production"
      # 2. Chuỗi kết quả: "jdbc:mysql://payment-db-production:3306/mydb"
      # 3. Step 3 Check: "payment-db-production" nằm giữa `//` và `:`
      # -> KẾT QUẢ MONG ĐỢI: MATCH ✅
      DB_CONN = "jdbc:mysql://${var.db_host_name}:3306/mydb"

      # CASE C: False Positive Trap (Bẫy Boundary)
      # Logic: Resource đích tên là "user" (Target 3).
      # Chuỗi nguồn chứa từ "superuser".
      # Nếu Boundary Check KÉM: Nó sẽ thấy "user" nằm trong "superuser" -> Match sai.
      # Nếu Boundary Check TỐT: Ký tự trước "user" là "r" (chữ cái) -> Invalid Boundary.
      # -> KẾT QUẢ MONG ĐỢI: NO MATCH (Bỏ qua) ❌
      DASHBOARD_URL = "https://superuser-dashboard.internal/login"

      # CASE D: Valid URL Match
      # Logic: Resource đích "user".
      # Chuỗi: "https://api.internal/v1/user/profile"
      # Ký tự trước "user" là `/`, sau là `/`.
      # -> KẾT QUẢ MONG ĐỢI: MATCH ✅ (Đây là tham chiếu hợp lệ)
      API_ENDPOINT = "https://api.internal/v1/user/profile"
    }
  }
}