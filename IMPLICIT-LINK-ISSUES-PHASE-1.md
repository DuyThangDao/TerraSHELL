Dưới đây là bức tranh toàn cảnh về các loại đứt gãy liên kết:

1. Hardcoded Internal Reference (Tình huống 1 của bạn)
Mô tả: Tài nguyên A tham chiếu tới Tài nguyên B (cả 2 đều nằm trong code .tf) bằng một thuộc tính định danh (như name, description) thay vì tham chiếu biến.

Ví dụ:

Resource SG: name = "web-sg"

Resource EC2: security_groups = ["web-sg"]

Đánh giá: Đây là trường hợp phổ biến nhất và là mục tiêu chính của module bạn.

2. Hardcoded External Reference / Ghost Node (Tình huống 2 của bạn)
Mô tả: Tài nguyên A tham chiếu tới một ID thực tế (sg-xxx, ami-xxx) không hề được định nghĩa trong bất kỳ file .tf nào.

Ví dụ:

Resource EC2: vpc_security_group_ids = ["sg-012345678"]

Đánh giá: Static Analysis thông thường sẽ bỏ qua. Giải pháp của bạn là tạo Ghost Node. Đây là trường hợp quan trọng thứ 2.

CÁC TRƯỜNG HỢP MỞ RỘNG (Nâng cao độ khó)
3. Dynamic String Interpolation (Chuỗi ghép động)
Đây là "kẻ thù" của việc so khớp chuỗi đơn giản.

Mô tả: Dev không hardcode chuỗi tĩnh "web-sg", mà dùng biến để ghép thành chuỗi.

Ví dụ:

var.env = "prod"

Resource SG: name = "prod-web-sg"

Resource EC2: security_groups = ["${var.env}-web-sg"]

Vấn đề:

Phase 1 (Terraform Graph) bị mù vì không thấy ref trực tiếp đến resource SG.

Module "Implicit Resolver" cơ bản (chỉ so sánh string ==) cũng sẽ bó tay vì "prod-web-sg" khác với chuỗi thô "${var.env}-web-sg".

Giải pháp (Cho luận văn): Bạn có thể liệt kê đây là một Hạn chế (Limitation) hoặc Future Work nếu không đủ thời gian làm tính năng "giải biến" (Variable Resolution).

4. Implicit via Third-Party Services (Trung gian thứ 3)
Đây là trường hợp được nhắc đến cụ thể trong bài báo gốc mục 6.1.

Mô tả: Hai tài nguyên không nói chuyện trực tiếp, mà thông qua một dịch vụ trung gian không được Terraform quản lý đầy đủ (như DNS).

Ví dụ (từ bài báo):

Resource A tạo ra một Database và đăng ký DNS record.

Resource B gọi đến Database thông qua tên miền DNS (lookup).

Terraform không thấy liên kết giữa A và B vì DNS lookup là hành động runtime.

Trích dẫn: "The second form of implicit communication is the reliance on third-party dependencies... e.g., DNS lookups".

Đánh giá: Trường hợp này cực khó phát hiện bằng Static Analysis. Bạn nên đưa vào phần "Phạm vi nghiên cứu" (Scope) để loại trừ nó ra, nói rõ là luận văn tập trung vào Identifier-based dependencies.

5. Tag-based Dependency (Phụ thuộc qua Tag)
Một số dịch vụ AWS hoạt động dựa trên việc "quét Tag".

Ví dụ: Bạn có một Lambda Function được cấu hình để "Chạy trên tất cả EC2 nào có tag Role = Worker".

Vấn đề: Trong code Terraform không hề có dòng nào nối Lambda với EC2. Mối liên kết này nằm trong logic của code ứng dụng (Code Python/NodeJS trong Lambda) hoặc cấu hình AWS EventBridge.

Đánh giá: Đây cũng là một dạng liên kết ngầm rất khó phát hiện nếu chỉ nhìn vào file .tf.

TỔNG KẾT CHIẾN LƯỢC CHO LUẬN VĂN
Để luận văn vừa sức nhưng vẫn có chiều sâu, tôi khuyên bạn nên chốt phạm vi (Scope) như sau:

Tập trung giải quyết triệt để:

Tình huống 1 (Internal Exact Match): Quét name/attribute khớp nhau.

Tình huống 2 (External/Ghost Node): Quét ID cứng dạng sg-, ami-...

Đề cập nhưng để ở phần "Hạn chế" hoặc "Hướng phát triển":

Tình huống 3 (Interpolation): "Trong phạm vi luận văn, chúng tôi tập trung vào chuỗi tĩnh. Việc phân tích chuỗi động phức tạp cần bộ giải biến (symbolic execution) sẽ được nghiên cứu sau."

Tình huống 4 (Third-party/DNS): Trích dẫn bài báo gốc để xác nhận đây là giới hạn chung của ngành.

Bạn đồng ý với việc khoanh vùng phạm vi vào Tình huống 1 và 2 chứ? Nếu đồng ý, chúng ta sẽ bắt đầu thiết kế giải thuật cho module Submodule.

////////////////////

Dưới đây là chi tiết Pipeline 5 Bước (5-Step Pipeline) hoàn chỉnh để giải quyết vấn đề tham chiếu gián tiếp trong Terraform. Quy trình này được thiết kế theo mô hình "Phễu lọc" (Filtering Funnel), đi từ độ chính xác cao nhất (Exact) xuống độ linh hoạt cao nhất (Fuzzy/Ghost).

Bước 1: Taint Analysis & Variable Resolution (Tiền xử lý & Phân giải biến)
Đây là bước nền tảng. Nếu không làm bước này, các bước sau sẽ không có dữ liệu để chạy.

Logic triển khai:

Xây dựng đồ thị phụ thuộc nội bộ của các biến (Variables, Locals, Module outputs).

Thực hiện kỹ thuật Constant Propagation (Lan truyền hằng số): Thay thế tất cả các tham chiếu biến (var.x, local.y) bằng giá trị chuỗi ký tự (Literal String) gốc của chúng.

Vấn đề giải quyết:

Developer hiếm khi hardcode trực tiếp ngay tại resource. Họ thường khai báo biến ở file variables.tf hoặc tính toán trong locals.

Tool cần "nhìn thấu" qua các lớp biến để thấy chuỗi thực sự.

Ví dụ:

Code: resource A { name = local.db_name } (trong đó local.db_name = "payment-db").

Kết quả Bước 1: Biến đổi thành resource A { name = "payment-db" }.

Bước 2: Exact Matching (So khớp chính xác tuyệt đối)
Đây là "Happy Path" - trường hợp lý tưởng nhất.

Logic triển khai:

Xây dựng Symbol Table chứa danh sách tất cả Resource ID và Resource Name trong dự án.

So sánh chuỗi nguồn (Source String) với tên Resource đích (Target Name).

Điều kiện: Source_String == Target_Name (Case-sensitive hoặc Case-insensitive tùy cấu hình).

Vấn đề giải quyết:

Implicit Dependency bị thiếu: Developer gõ đúng tên resource nhưng quên dùng cú pháp tham chiếu biến (quên ${...}), làm mất dependency graph của Terraform.

Ví dụ:

Source: db_instance = "payment-db"

Target: resource "aws_db_instance" "payment-db" {...}

Kết quả: MATCH (Hard Link).

Bước 3: Boundary-aware Substring Matching (So khớp chuỗi con có kiểm tra biên)
Đây là bước quan trọng nhất để xử lý các chuỗi phức tạp (ARN, URL).

Logic triển khai:

Duyệt qua danh sách Resource đích. Kiểm tra: Target_Name có nằm trong Source_String không?

Boundary Check (Kiểm tra biên - Critical): Nếu tìm thấy, kiểm tra ký tự liền trước và liền sau của Target_Name trong Source_String.

Hợp lệ nếu ký tự biên là: :, /, ., @, -, " hoặc đầu/cuối dòng.

Không hợp lệ nếu ký tự biên là chữ cái hoặc số (để tránh matching nhầm từ vựng).

Vấn đề giải quyết:

Complex Strings: Resource được tham chiếu thông qua ARN, Connection String (JDBC), SQS URL, hoặc Domain Name.

Giải quyết triệt để vấn đề "User vs Superuser" (Tên ngắn nằm lọt trong tên dài nhưng không liên quan).

Ví dụ:

Source: Resource = "arn:aws:s3:::finance-data-bucket"

Target: resource "aws_s3_bucket" "finance-data-bucket" {...}

Logic: Tìm thấy "finance-data-bucket" nằm trong chuỗi ARN. Ký tự trước là :, sau là " (hợp lệ).

Kết quả: MATCH (Hard Link).

Bước 4: Fuzzy & Heuristic Matching (So khớp mờ & Suy luận)
Bước "Thông minh" để bắt lỗi con người và biến thể đặt tên.

Logic triển khai:

Type Filtering (Heuristic): Dựa vào ngữ cảnh (ví dụ: thuộc tính là db_host), chỉ lọc danh sách đích là các Database Resource -> Giảm không gian tìm kiếm.

String Distance: Tính khoảng cách Levenshtein hoặc độ tương đồng Jaccard giữa Source_String và Target_Name.

Threshold: Nếu độ tương đồng > 85% (ngưỡng do bạn đặt), đánh dấu là tìm thấy.

Vấn đề giải quyết:

Typo: Lỗi chính tả (gõ thiếu/thừa ký tự).

Naming Variants: Khác biệt nhỏ do quy tắc đặt tên (VD: prod_db vs prod-db).

Dynamic Names: Tên có suffix ngẫu nhiên (VD: app-server vs app-server-x9z).

Ví dụ:

Source: host = "paymnt-db-prod" (Gõ thiếu chữ 'e').

Target: resource "aws_db_instance" "payment-db-prod".

Kết quả: MATCH (Soft Link / Potential Edge) - Kèm cảnh báo.

Bước 5: Ghost Node Creation (Tạo nút ảo / External Entity)
Bước cuối cùng (Fallback) để đảm bảo tính toàn vẹn của Threat Model.

Logic triển khai:

Nếu cả 4 bước trên đều trả về kết quả False (không tìm thấy resource nào trong code nội bộ).

Hệ thống kết luận: Đây là tham chiếu đến tài nguyên bên ngoài (External Reference).

Tự động khởi tạo một Node mới trên đồ thị với nhãn External Entity.

Vẽ cạnh nối từ Resource đang xét tới Node ảo này.

Vấn đề giải quyết:

Hardcoded External Reference: Kết nối tới Legacy System, 3rd Party API, hoặc Resource tạo tay không quản lý bằng Terraform.

Giúp phát hiện rủi ro rò rỉ dữ liệu ra khỏi biên giới hệ thống (Trust Boundary Crossing).

Ví dụ:

Source: endpoint = "oracle-legacy.corp.internal"

Target: Không tìm thấy trong file .tf nào.

Kết quả: Tạo Node [External: oracle-legacy.corp.internal] và vẽ mũi tên kết nối.

Tóm tắt giá trị của Pipeline này:
Bước 1 & 2: Đảm bảo độ chính xác cơ bản.

Bước 3: Giải quyết kỹ thuật khó nhất (ARN/URL Parsing) mà không cần Regex phức tạp.

Bước 4: Thể hiện tính "thông minh" (xử lý lỗi con người).

Bước 5: Đảm bảo bao quát rủi ro bảo mật (Threat Coverage).

