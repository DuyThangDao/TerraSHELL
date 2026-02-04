# Tài liệu Kỹ thuật: Step 4 - Fuzzy & Heuristic Matching

## 1. Tổng quan (Overview)

**Fuzzy & Heuristic Matching** là lớp phòng thủ cuối cùng trong Pipeline giải quyết phụ thuộc ẩn (Implicit Dependency Resolution). Sau khi các bước trước đã xử lý các trường hợp chính xác (Step 2) và lồng ghép (Step 3), Step 4 đóng vai trò là "lưới vét" để phát hiện các liên kết tiềm năng bị bỏ sót do lỗi của con người hoặc sự không nhất quán trong quy ước đặt tên.

* **Đầu vào:** Đồ thị tài nguyên (Resource Graph) sau khi đã chạy Step 1, 2, 3.
* **Đầu ra:** Các cạnh `REF` mới với nhãn `method='fuzzy_match'` và điểm tin cậy (`confidence score`).
* **Mục tiêu:** Bắt lỗi chính tả (Typos), biến thể tên gọi (Naming Variants) và các quy ước ngầm định.

## 2. Vấn đề giải quyết (Problem Statement)

Trong thực tế phát triển Infrastructure as Code (IaC), code không phải lúc nào cũng máy móc và chuẩn xác tuyệt đối. Các vấn đề sau thường xuyên xảy ra làm gãy đứt liên kết đồ thị:

1. **Lỗi chính tả (Typos):** Developer gõ sai ký tự nhưng vì cấu hình được hardcode nên hệ thống vẫn chạy (hoặc lỗi nhưng ta cần phát hiện để cảnh báo).
* *Ví dụ:* `db_host = "paymnt-db"` (thiếu 'e') so với `payment-db`.


2. **Không nhất quán quy ước (Naming Inconsistency):** Sự trộn lẫn giữa `snake_case` (Python/Terraform chuẩn) và `kebab-case` (AWS Resources).
* *Ví dụ:* Biến môi trường `QUEUE_URL_ORDER_EVENTS` so với tên queue `queue-url-order-events`.


3. **Biến thể hậu tố (Suffix Variants):** Thêm số hoặc môi trường vào tên resource một cách ngẫu hứng.
* *Ví dụ:* Code gọi tới `redis-cache`, nhưng tên thật là `redis-cache-01` hoặc `redis-cache-master`.



## 3. Kiến trúc & Logic (Architecture & Logic)

Step 4 sử dụng chiến lược **Type-Aware Fuzzy Matching** (So khớp mờ nhận biết loại) để đảm bảo hiệu năng và giảm thiểu dương tính giả (False Positives).

### 3.1. Type Filtering (Bộ lọc loại Resource)

Để tránh việc so sánh vô nghĩa (ví dụ: so sánh tên Database với tên S3 Bucket), hệ thống sử dụng **Heuristic Map** để khoanh vùng phạm vi tìm kiếm.

* **Logic:** Dựa vào tên thuộc tính nguồn (Source Property Name) để đoán loại Resource đích.
* **Bảng quy tắc (Heuristic Map):**
* Thuộc tính chứa `bucket`, `s3`  Chỉ tìm trong danh sách `aws_s3_bucket`.
* Thuộc tính chứa `db`, `host`, `rds`  Chỉ tìm trong `aws_db_instance`, `aws_rds_cluster`.
* Thuộc tính chứa `queue`, `sqs`  Chỉ tìm trong `aws_sqs_queue`.



### 3.2. Thuật toán so khớp chuỗi (String Similarity Algorithms)

Sử dụng thuật toán **Levenshtein Distance** (hoặc Sequence Matcher) để tính toán độ tương đồng giữa hai chuỗi ký tự.

* **Công thức:** Độ tương đồng được chuẩn hóa về thang điểm `0.0` đến `1.0`.
* **Ngưỡng (Threshold):** Chỉ chấp nhận các kết quả có điểm  (85%).

### 3.3. Quy trình thực thi (Execution Flow)

1. **Build Target Cache:** Gom nhóm tất cả Resource đích vào bộ nhớ đệm, phân loại theo Resource Type.
2. **Scan Source Properties:** Duyệt qua tất cả thuộc tính của Resource nguồn.
3. **Heuristic Check:** Kiểm tra xem tên thuộc tính có gợi ý loại Resource đích nào không?
* *Nếu có:* Lấy danh sách ứng viên từ Cache tương ứng.
* *Nếu không:* Bỏ qua để tối ưu hiệu năng.


4. **Calculate & Match:** Tính điểm tương đồng giữa giá trị nguồn và từng ứng viên.
5. **Create Link:** Nếu điểm số  Threshold và chưa có liên kết, tạo cạnh mới.

## 4. Ví dụ kịch bản (Test Scenarios)

Dưới đây là các trường hợp điển hình mà Step 4 giải quyết:

### Case A: Lỗi chính tả (Typo Correction)

* **Nguồn (Lambda):** `DB_HOST = "inventory-db-prodution"` (Thiếu chữ 'c').
* **Đích (RDS):** `identifier = "inventory-db-production"`.
* **Kết quả:**
* Step 2 (Exact): Thất bại.
* Step 4 (Fuzzy): **Thành công** (Score ~0.98).



### Case B: Quy ước Snake_case vs Kebab-case

* **Nguồn (App Config):** `TARGET_BUCKET = "data_lake_raw_storage"`.
* **Đích (S3):** `bucket = "data-lake-raw-storage"`.
* **Kết quả:**
* Step 2 (Exact): Thất bại.
* Step 4 (Fuzzy): **Thành công** (Score ~0.88 - do thay thế `_` bằng `-`).



### Case C: Suffix biến động (Dynamic Suffix)

* **Nguồn (EC2 UserData):** `echo "Connecting to logs-cluster..."`.
* **Đích (Elasticache):** `cluster_id = "logs-cluster-primary"`.
* **Kết quả:**
* Step 3 (Boundary): Có thể thất bại nếu không xử lý biên tốt.
* Step 4 (Fuzzy): **Thành công** (Score > 0.85 do chuỗi con chiếm phần lớn độ dài).



## 5. Giới hạn & Lưu ý (Limitations)

1. **Hiệu năng:** Step 4 tốn tài nguyên tính toán hơn Step 2 và 3 do độ phức tạp của thuật toán so sánh chuỗi (). Do đó, **Type Filtering** là bắt buộc để giảm không gian tìm kiếm.
2. **Độ tin cậy (Confidence):** Các liên kết tạo ra bởi Step 4 được gán nhãn là "Tiềm năng" (Potential). Trong giao diện người dùng (nếu có), các liên kết này nên được hiển thị khác biệt (ví dụ: nét đứt) để người dùng kiểm tra lại.
3. **Dương tính giả:** Dù đã lọc kỹ, vẫn có khả năng bắt nhầm nếu 2 resource có tên quá giống nhau (ví dụ: `app-db-v1` và `app-db-v2` có thể bị coi là typo của nhau).

---

**Trạng thái hiện tại:** Đã có module Python `FuzzyMatcher` tích hợp sẵn logic Type Filtering và Sequence Matching. Sẵn sàng tích hợp vào Pipeline chính.