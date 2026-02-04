Trong Terraform, các tài nguyên AWS (Resources) không đứng cô lập mà liên kết chặt chẽ với nhau để tạo thành một hạ tầng hoàn chỉnh. Việc hiểu rõ **tất cả các cách liên kết** này là cực kỳ quan trọng để công cụ của bạn (Dependency Graph) không bị bỏ sót (Missing Links).

Dưới đây là 5 cách liên kết chính, được sắp xếp từ **Tường minh (Explicit)** đến **Ngầm định (Implicit)**:

---

### 1. Direct Attribute Reference (Liên kết Tường minh)

Đây là cách chuẩn mực nhất và dễ phát hiện nhất. Terraform tự động xây dựng Dependency Graph dựa trên cú pháp này.

* **Cơ chế:** Resource B sử dụng thuộc tính đầu ra (Output Attribute) của Resource A (thường là `.id`, `.arn`, `.endpoint`).
* **Cú pháp:** `resource_type.logical_name.attribute`
* **Ví dụ:** EC2 Instance gắn vào Security Group.

```hcl
resource "aws_security_group" "web_sg" {
  name = "allow_http"
}

resource "aws_instance" "web_server" {
  ami = "ami-12345678"
  instance_type = "t2.micro"
  
  # LIÊN KẾT TƯỜNG MINH
  vpc_security_group_ids = [aws_security_group.web_sg.id] 
}

```

* **Xử lý bởi tool của bạn:** Dễ dàng parse được ngay từ AST (Abstract Syntax Tree) hoặc `terraform plan`.

---

### 2. Implicit String Reference (Liên kết Ngầm định qua Chuỗi)

Đây là cơn ác mộng của Static Analysis và là lý do bạn cần **Step 2 (Exact Match)** và **Step 3 (Boundary Match)**. Lập trình viên không tham chiếu biến mà "hard-code" giá trị.

* **Cơ chế:** Resource B chứa một chuỗi ký tự (String) trùng khớp với Tên hoặc ARN của Resource A.
* **Các dạng phổ biến:**
* **Physical ID:** Tên tài nguyên (`bucket="my-app-logs"`).
* **ARN:** Chuỗi định danh AWS (`role="arn:aws:iam::...:role/admin"`).
* **Connection String/URL:** (`db_url="jdbc:mysql://db-prod:3306..."`).
* **JSON Policy:** Nhúng ARN vào trong JSON string (IAM Policy, Bucket Policy).



```hcl
resource "aws_s3_bucket" "logs" {
  bucket = "company-logs-prod" # Physical ID
}

resource "aws_lambda_function" "processor" {
  function_name = "log-processor"
  
  environment {
    variables = {
      # LIÊN KẾT NGẦM ĐỊNH (Step 2/3 phải bắt cái này)
      BUCKET_NAME = "company-logs-prod" 
    }
  }
}

```

---

### 3. Data Source Reference (Liên kết qua Tra cứu)

Resource A và Resource B có thể không nằm cùng một file Terraform, hoặc Resource A đã được tạo từ trước (bằng tay hoặc stack khác). Resource B liên kết với A thông qua `data`.

* **Cơ chế:** Terraform "hỏi" AWS về thông tin của một resource đã tồn tại, sau đó dùng thông tin đó để tạo resource mới.
* **Ví dụ:** Tìm VPC ID theo Tags rồi tạo Subnet vào đó.

```hcl
# Tìm VPC đã tồn tại (Lookup)
data "aws_vpc" "existing_vpc" {
  tags = {
    Name = "Production-VPC"
  }
}

resource "aws_subnet" "new_subnet" {
  # Liên kết với VPC tìm được ở trên
  vpc_id = data.aws_vpc.existing_vpc.id 
  cidr_block = "10.0.1.0/24"
}

```

* **Xử lý:** Tool của bạn cần coi `data` như một node trung gian hoặc biên dịch nó thành một cạnh liên kết tới resource thực tế (nếu resource đó nằm trong cùng Graph).

---

### 4. Meta-Argument `depends_on` (Liên kết Thứ tự)

Đôi khi không có dữ liệu nào được truyền từ A sang B, nhưng B bắt buộc phải đợi A tạo xong mới được chạy.

* **Cơ chế:** Chỉ định rõ ràng thứ tự khởi tạo.
* **Ví dụ:** S3 Bucket phải được tạo xong thì mới gán Policy vào được (dù Policy resource đã tham chiếu bucket, nhưng đôi khi cần explicit wait để tránh race condition).

```hcl
resource "aws_s3_bucket" "b" { ... }

resource "aws_s3_bucket_public_access_block" "example" {
  bucket = aws_s3_bucket.b.id
  
  # LIÊN KẾT THỨ TỰ
  depends_on = [aws_s3_bucket.b] 
}

```

* **Ý nghĩa:** Đây là một cạnh `DEPENDS_ON` trong graph, tuy nhiên nó không mang ý nghĩa về luồng dữ liệu (Data Flow) mà là luồng triển khai (Deployment Flow).

---

### 5. Indirect Reference via Variables/Locals (Liên kết Gián tiếp)

Resource A và B không nói chuyện trực tiếp, mà thông qua một biến trung gian (`local` hoặc `var`).

* **Cơ chế:** A -> Local Variable -> B.
* **Ví dụ:**

```hcl
locals {
  # Biến trung gian
  bucket_name = aws_s3_bucket.main.bucket 
}

resource "aws_s3_bucket" "main" { ... }

resource "aws_lambda_function" "app" {
  environment {
    variables = {
      # Liên kết gián tiếp qua local
      TARGET = local.bucket_name 
    }
  }
}

```

* **Xử lý:** Đây là nhiệm vụ của **Taint Analysis (Step 1)** để giải quyết (resolve) giá trị của `local.bucket_name` về lại `aws_s3_bucket.main`.

---

### Tổng kết dưới dạng Diagram

Để dễ hình dung cho việc xây dựng tool, bạn có thể xem sơ đồ các kiểu liên kết này:

| Loại Liên kết | Mức độ tường minh | Bước xử lý trong Pipeline của bạn |
| --- | --- | --- |
| **Attribute Ref** (`res.id`) | Cao nhất | Parser (Ban đầu) |
| **Variable/Local** (`var.x`) | Trung bình | Step 1 (Taint Analysis) |
| **Physical Name** (`"name"`) | Thấp | Step 2 (Exact Match) |
| **Complex String** (`ARN/URL`) | Rất thấp (Ẩn) | Step 3 (Boundary Match) |
| **Data Source** | Trung bình | Parser / Step 2 |

Việc bạn mở rộng Step 2 để bắt **Physical Name** và dùng Step 3 để bắt **ARN/URL** là bạn đang bao phủ gần như trọn vẹn các vùng "xám" và "tối" trong bản đồ liên kết này.