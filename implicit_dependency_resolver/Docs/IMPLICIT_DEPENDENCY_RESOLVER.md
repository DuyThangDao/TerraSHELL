# TÀI LIỆU KỸ THUẬT: PIPELINE PHÁT HIỆN LIÊN KẾT NGẦM (IMPLICIT DEPENDENCY DISCOVERY)

## Tổng quan (Overview)

Hệ thống phân tích tĩnh thông thường (Static Analysis) chỉ phát hiện được các liên kết tường minh (dựa trên tham chiếu biến `resource.id`). Pipeline 5 bước này được thiết kế để tìm ra các "Missing Links" – các liên kết bị ẩn do lập trình viên sử dụng chuỗi hardcode, biến môi trường, hoặc cấu hình động.

Mục tiêu: Xây dựng đồ thị phụ thuộc (Dependency Graph) đầy đủ nhất để phục vụ Threat Modeling và Security Audit.

---

## BƯỚC 1: TAINT ANALYSIS & VARIABLE RESOLUTION (Tiền xử lý & Phân giải biến)

### 1. Mục đích

Biến đổi các biểu thức Terraform động thành các giá trị chuỗi tĩnh (Literal Strings) để các thuật toán so khớp ở bước sau có thể đọc hiểu được. Đây là bước **khử nhiễu** dữ liệu.

### 2. Vấn đề giải quyết

* Developer khai báo giá trị ở `variables.tf`, tính toán trong `locals`, hoặc lấy từ `module outputs`.
* Code tham chiếu: `bucket = local.bucket_name`. Máy tính không biết `local.bucket_name` là gì nếu không truy vết ngược lại.

### 3. Logic triển khai

1. **Build Variable Graph:** Xây dựng đồ thị phụ thuộc nội bộ giữa các biến (Var -> Local -> Output).
2. **Constant Propagation (Lan truyền hằng số):**
* Duyệt từ các node lá (giá trị tĩnh) lan truyền lên trên.
* Giải quyết các hàm cơ bản: `join`, `format` (nếu có thể).
* Xử lý nội suy chuỗi (String Interpolation): `"app-${var.env}"` -> `"app-prod"`.


3. **Output:** Một map chứa các thuộc tính của resource đã được giải mã (`taint_resolved_properties`).

### 4. Ví dụ minh họa

* **Input Code:**
```hcl
variable "env" { default = "prod" }
locals { db_name = "payment-${var.env}" }
resource "aws_db_instance" "main" { identifier = local.db_name }

```


* **Output sau Bước 1:**
* `aws_db_instance.main.identifier` = `"payment-prod"`



---

## BƯỚC 2: ENRICHED EXACT MATCHING (So khớp chính xác mở rộng)

### 1. Mục đích

Xử lý các trường hợp "Happy Path" nơi giá trị chuỗi khớp hoàn toàn 100% với định danh của Resource. Đây là bước tối ưu hóa hiệu năng () trước khi sang các bước phức tạp.

### 2. Vấn đề giải quyết

* **Logical ID Reference:** Tham chiếu bằng tên trong code (`"aws_s3_bucket.main"`).
* **Physical ID Hardcoding:** Tham chiếu bằng tên thực tế của resource (`"company-logs-bucket"`).

### 3. Logic triển khai

1. **Xây dựng Enriched Symbol Table (Quan trọng):**
* Quét toàn bộ Resource trong Graph.
* Lưu trữ **Logical ID**: `name`, `resource_name`.
* Lưu trữ **Physical ID**: Trích xuất từ các thuộc tính định danh (`bucket` của S3, `name` của SQS, `identifier` của RDS, `function_name` của Lambda).


2. **Matching Algorithm:**
* Lấy danh sách chuỗi từ Bước 1.
* Tra cứu trực tiếp trong Symbol Table (Hash Map Lookup).
* Nếu tồn tại -> **MATCH**.



### 4. Ví dụ minh họa

* **Symbol Table:**
* `"log_bucket"` (Logical) -> ID: 101
* `"company-logs-prod"` (Physical) -> ID: 101


* **Trường hợp 1:** `bucket = "log_bucket"` -> Match ID 101.
* **Trường hợp 2:** `bucket = "company-logs-prod"` -> Match ID 101.

---

## BƯỚC 3: BOUNDARY-AWARE SUBSTRING MATCHING (So khớp chuỗi con có biên)

### 1. Mục đích

"Thám tử" của pipeline. Chuyên xử lý các chuỗi phức tạp chứa định danh resource bên trong, nhưng bị bao bọc bởi các tiền tố/hậu tố kỹ thuật.

### 2. Vấn đề giải quyết

* **ARN:** `arn:aws:s3:::my-bucket`
* **Connection Strings:** `jdbc:mysql://my-db:3306/data`
* **URLs:** `https://sqs.us-east-1.amazonaws.com/123/my-queue`
* **Dương tính giả (False Positives):** Tránh việc tìm thấy chữ `os` trong `localhost`.

### 3. Logic triển khai

1. **Filter Input:** Chỉ quét các chuỗi có dấu hiệu phức tạp (chứa `arn:`, `http`, `:`, `.`).
2. **Substring Scan:** Kiểm tra xem *Symbol* (từ Symbol Table Bước 2) có nằm trong chuỗi nguồn không.
3. **Boundary Check (Kiểm tra biên):**
* Nếu tìm thấy, kiểm tra ký tự liền trước (`pre_char`) và liền sau (`post_char`).
* **Hợp lệ (Valid):** `pre/post_char` thuộc tập `{:, /, ., @, -, ", space, None}`.
* **Không hợp lệ (Invalid):** `pre/post_char` là Chữ cái (a-z) hoặc Số (0-9).


4. **Kết luận:** Chỉ tạo liên kết nếu Boundary Check trả về `True`.

### 4. Ví dụ minh họa

* **Target:** Resource tên `finance-db`.
* **Source:** `"jdbc:postgresql://finance-db.internal:5432"`
* Tìm thấy `finance-db`.
* Trước là `/` (Hợp lệ).
* Sau là `.` (Hợp lệ).
* => **LINK CREATED**.


* **Source sai:** `"finance-db-backup"`
* Trước là `"` (Hợp lệ).
* Sau là `-` (Tùy cấu hình, nhưng nếu `-` là valid boundary thì match, nếu coi là phần của tên thì không). *Lưu ý: Thường `-` được cấu hình là Valid boundary để bắt prefix/suffix.*



---

## BƯỚC 4: FUZZY & HEURISTIC MATCHING (So khớp mờ & Suy luận)

### 1. Mục đích

Bắt các lỗi do con người (Typo) hoặc các quy ước đặt tên biến thể nhẹ mà thuật toán chính xác bỏ qua.

### 2. Vấn đề giải quyết

* **Typos:** Gõ thiếu/sai ký tự (`proddb` thay vì `prod-db`).
* **Naming Variants:** `app_server` vs `app-server`.
* **Dynamic Suffix:** `web-server-01` tham chiếu tới `web-server`.

### 3. Logic triển khai

1. **Type Filtering (Tối ưu hóa):**
* Nếu thuộc tính nguồn là `db_host`, chỉ so sánh với danh sách các Resource là Database (RDS). Không so sánh với S3 hay Lambda.


2. **String Distance Calculation:**
* Sử dụng thuật toán **Levenshtein Distance** hoặc **Jaccard Similarity**.


3. **Thresholding:**
* Nếu độ tương đồng > **85%** (Ngưỡng cấu hình), đánh dấu là **Potential Link**.
* Gán nhãn `CONFIDENCE: LOW/MEDIUM` cho cạnh này để người dùng review.



### 4. Ví dụ minh họa

* **Target:** `payment-service-db`
* **Source:** `paymnt-service-db` (Thiếu chữ 'e').
* **Kết quả:** Levenshtein Distance nhỏ -> Tạo **Soft Link** (Cảnh báo: "Có thể là typo?").

---

## BƯỚC 5: GHOST NODE CREATION (Tạo Node Ảo / External Entity)

### 1. Mục đích

Lưới an toàn cuối cùng. Nếu một chuỗi trông giống Endpoint/ARN mà không khớp với bất kỳ resource nội bộ nào (qua 4 bước trên), hệ thống kết luận đó là tài nguyên bên ngoài.

### 2. Vấn đề giải quyết

* **External APIs:** Google Maps API, Stripe, Auth0.
* **Legacy Systems:** Database cũ on-premise không quản lý bằng Terraform hiện tại.
* **Cross-Stack References:** Tài nguyên thuộc về một file Terraform state khác.

### 3. Logic triển khai

1. **Condition:** Sau khi chạy xong Bước 1-4, nếu chuỗi vẫn chưa được resolve thành Link.
2. **Validation:** Kiểm tra xem chuỗi có đúng định dạng URL/IP/Domain/ARN hợp lệ không (để tránh tạo node rác từ chuỗi văn bản thường).
3. **Node Creation:**
* Tạo Node mới: `Label: ExternalEntity`, `Name: <Chuỗi URL/ARN>`.
* Tạo cạnh `REF` từ Resource nguồn tới Node ảo này.



### 4. Ví dụ minh họa

* **Source:** `api_endpoint = "https://legacy-crm.corp.internal/v1"`
* **Process:** Bước 1-4 không tìm thấy resource nào tên `legacy-crm`.
* **Action:** Tạo Node ảo `ExternalEntity: legacy-crm.corp.internal`.
* **Ý nghĩa bảo mật:** Phát hiện luồng dữ liệu đi ra khỏi biên giới hệ thống (Trust Boundary Crossing).

---

## TỔNG KẾT LUỒNG DỮ LIỆU (DATA FLOW SUMMARY)

| Bước | Đầu vào chính | Kỹ thuật lõi | Đầu ra | Loại liên kết |
| --- | --- | --- | --- | --- |
| **1** | Raw Terraform Code | Constant Propagation | Resolved Strings | N/A (Chuẩn bị dữ liệu) |
| **2** | Resolved Strings | Hash Map Lookup | Resource IDs | **Hard Link** (Chắc chắn 100%) |
| **3** | Complex Strings (ARN/URL) | Boundary Check | Resource IDs | **Hard Link** (Chắc chắn 99%) |
| **4** | Typo/Variants | Levenshtein/Jaccard | Resource IDs | **Soft Link** (Cần review) |
| **5** | Unresolved Endpoints | Regex Validation | Ghost Nodes | **External Link** |