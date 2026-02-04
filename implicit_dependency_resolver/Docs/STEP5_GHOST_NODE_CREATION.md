# PHASE 1 - STEP 5: GHOST NODE CREATION

**(Tạo Node Ảo & Phân giải Thực thể Bên ngoài)**

### 1. Tổng quan (Overview)

**Step 5** là "lưới quét cuối cùng" (Final Safety Net) trong Pipeline xử lý Dependency. Nhiệm vụ của nó là phát hiện và vật chất hóa (materialize) các mối quan hệ trỏ ra bên ngoài phạm vi quản lý của Terraform hiện tại.

Những node này được gọi là **"Ghost Nodes"** (hoặc `ExternalEntity`) vì chúng tồn tại trong cấu hình (config) nhưng không có file định nghĩa `.tf` tương ứng trong dự án.

### 2. Vấn đề giải quyết (Problem Statement)

Các bước 1-4 chỉ tập trung vào việc nối các Resource **nội bộ** (Internal). Tuy nhiên, một hệ thống thực tế luôn giao tiếp với thế giới bên ngoài. Step 5 giải quyết 3 điểm mù lớn:

1. **3rd Party Integration:** Kết nối tới SaaS (Stripe, Auth0, Google Maps API...).
2. **Legacy Systems:** Kết nối tới các Database/Server cũ (On-premise) qua IP cứng.
3. **Cross-Account/Cross-Stack:** Tham chiếu tới tài nguyên AWS thuộc tài khoản khác hoặc State file khác qua ARN.

### 3. Logic Cốt lõi (Core Logic)

Step 5 sử dụng chiến lược **"Smart Merge & Strict Filtering"** (Hợp nhất thông minh & Lọc chặt chẽ):

#### A. Quy trình xử lý dữ liệu (Data Pipeline)

1. **Smart Merge (Hợp nhất):** Với mỗi Resource, hệ thống lấy `properties` gốc và ghi đè (overlay) bằng `taint_resolved_properties` (kết quả từ Step 1).
* *Mục đích:* Đảm bảo quét được giá trị thực tế (ví dụ: `1.2.3.4`) thay vì tên biến vô nghĩa (`${var.db_ip}`).


2. **Flatten & Filter Keys:** Làm phẳng cấu trúc JSON, đồng thời loại bỏ các Key siêu dữ liệu (`id`, `type`, `parent_id`, `tags`) để giảm nhiễu.
3. **Extraction (Trích xuất):** Quét giá trị qua bộ Regex đặc thù để tìm: **ARN**, **URL**, **IP**, **DOMAIN**.

#### B. Cơ chế Bảo vệ (Safety Mechanisms)

Để tránh False Positive (Dương tính giả), Step 5 áp dụng 3 lớp khóa:

1. **Terraform Syntax Blocker:** Chặn ngay lập tức các chuỗi bắt đầu bằng từ khóa nội bộ (`rule.*`, `var.*`, `module.*`, `aws_*`). *Đây là fix quan trọng cho vấn đề `rule.allow`.*
2. **Internal Exclusion:** Nếu chuỗi tìm thấy trùng tên với một Resource nội bộ đã tồn tại -> **BỎ QUA** (Để Step 2, 3, 4 xử lý).
3. **Bad TLDs Filter:** Chặn các domain giả mạo có đuôi `.local`, `.internal`, `.tf`, `.json`.

#### C. Over-Approximation & Confidence Scoring

Hệ thống chấp nhận quét cả `description` để tìm Shadow IT (kết nối ngầm), nhưng phân loại độ tin cậy:

* **High Confidence:** Nếu link tìm thấy trong các trường cấu hình (`endpoint`, `url`, `host`).
* **Low Confidence:** Nếu link tìm thấy trong văn bản (`description`, `comment`).

### 4. Định nghĩa Node & Edge

* **Node Mới:**
* **Label:** `ExternalEntity`
* **Properties:**
* `name`: Giá trị trích xuất (vd: `https://api.stripe.com`)
* `type`: Loại nhận diện (`URL`, `IP`, `ARN`, `DOMAIN`)
* `created_by`: `"step5_ghost"`




* **Edge Mới:**
* **Type:** `REF`
* **Properties:**
* `method`: `"ghost_node"`
* `confidence`: `"high"` hoặc `"low"`
* `source_key`: Tên thuộc tính chứa liên kết (vd: `payment_gateway_url`).





### 5. Ví dụ Minh họa (Scenarios)

#### Case 1: SaaS API (High Confidence)

* **Code:** `environment { STRIPE_URL = "https://api.stripe.com" }`
* **Xử lý:** Regex URL bắt được chuỗi. Không vi phạm Syntax Blocker.
* **Kết quả:** `(Lambda) -[REF {conf: high}]-> (Ghost: https://api.stripe.com)`

#### Case 2: Legacy IP in Description (Low Confidence)

* **Code:** `description = "Connects to Legacy DB at 192.168.1.50"`
* **Xử lý:**
* Smart Merge lấy được chuỗi description.
* Regex IP bắt được `192.168.1.50`.
* Key là `description` -> Đánh dấu Low Confidence.


* **Kết quả:** `(SG Rule) -[REF {conf: low}]-> (Ghost: 192.168.1.50)`

#### Case 3: Terraform Internal Ref (Blocked)

* **Code:** `to_port = rule.allow` (Giả sử biến local tên `rule`)
* **Xử lý:**
* Regex Domain bắt được `rule.allow`.
* **Blocker:** Phát hiện prefix `rule.` -> **DROP**.


* **Kết quả:** Không tạo node rác.

### 6. Tổng kết Pipeline (Flowchart)

```mermaid
graph TD
    A[Start: Iterate Resources] --> B{Has Taint Resolved?}
    B -- Yes --> C[Merge Resolved Props into Raw Props]
    B -- No --> D[Use Raw Props]
    C --> D
    D --> E[Filter Ignored Keys \n(id, type, tags...)]
    E --> F[Extract Candidates via Regex \n(ARN, URL, IP, Domain)]
    F --> G{Is Terraform Syntax?\n(rule.*, var.*)}
    G -- Yes --> H[Discard Candidate]
    G -- No --> I{Is Internal Resource?}
    I -- Yes --> H
    I -- No --> J[Create 'ExternalEntity' Node]
    J --> K[Create 'REF' Edge]
    K --> L{Source Key in\nConfig?}
    L -- Yes --> M[Set Confidence = HIGH]
    L -- No --> N[Set Confidence = LOW]

```

### 7. Scripts liên quan

* **Logic:** `implicit_dependency_resolver/ghost_node.py` (hoặc nằm chung file chạy).
* **Execution:** `phase1_ghost_node.py`
* **Input:** Graph Database (đã chạy Step 1).
* **Output:** Các node màu tím (`ExternalEntity`) trên đồ thị.