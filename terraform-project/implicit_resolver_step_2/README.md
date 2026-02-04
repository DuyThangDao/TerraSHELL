# Test Project: Step 2 - Exact Matching

## Mục đích

Project này được thiết kế để kiểm tra độ chính xác của **Step 2: Exact Matching** trong module `implicit_dependency_resolver`.

## Cấu trúc Test Cases

### Positive Cases (Should MATCH ✓)

| Test Case | Source Resource | Target Resource | Expected Link | Description |
|-----------|----------------|-----------------|---------------|-------------|
| **TC1** | `aws_lambda_function.processor` | `aws_sqs_queue.order_queue` | Lambda → SQS | Variable resolution + Physical ID match |
| **TC2** | `aws_lambda_function.processor` | `aws_s3_bucket.data_bucket` | Lambda → S3 | Logical ID match (`data_bucket`) |
| **TC3** | `aws_lambda_function.processor` | `aws_s3_bucket.data_bucket` | Lambda → S3 | Variable interpolation → Physical ID match |
| **TC4** | `aws_instance.web_server` | `aws_security_group.web_sg` | EC2 → Security Group | Hardcoded Security Group name |
| **TC5** | `aws_db_instance.app_db` | `aws_subnet.private_subnet` | RDS → Subnet | Hardcoded Subnet name (from tags.Name) |
| **TC6** | `aws_instance.multi_sg_server` | `aws_security_group.sg1` | EC2 → SG1 | Multiple matches (first) |
| **TC6** | `aws_instance.multi_sg_server` | `aws_security_group.sg2` | EC2 → SG2 | Multiple matches (second) |
| **TC13** | `aws_lambda_function.case_test` | `aws_db_instance.payment_db` | Lambda → RDS | Case-insensitive match (lowercase) |
| **TC14** | `aws_lambda_function.case_test` | `aws_db_instance.payment_db` | Lambda → RDS | Case-insensitive match (uppercase) |
| **TC16** | `aws_lambda_function.nested_test` | `aws_db_instance.payment_db` | Lambda → RDS | Nested structure extraction |
| **TC16** | `aws_lambda_function.nested_test` | `aws_sqs_queue.order_queue` | Lambda → SQS | Nested structure extraction |
| **TC16** | `aws_lambda_function.nested_test` | `aws_s3_bucket.data_bucket` | Lambda → S3 | Nested structure extraction |

**Total Expected Matches: 13 links**

### Negative Cases (Should NOT MATCH ✗)

| Test Case | Source Resource | Value | Reason | Expected Behavior |
|-----------|-----------------|-------|--------|-------------------|
| **TC7** | `aws_lambda_function.filter_test` | `arn:aws:rds:...` | ARN format | Filtered out (Step 3 handles) |
| **TC8** | `aws_lambda_function.filter_test` | `https://api...` | URL format | Filtered out (Step 3 handles) |
| **TC9** | `aws_lambda_function.filter_test` | `""` | Empty string | Filtered out (len < 2) |
| **TC10** | `aws_lambda_function.filter_test` | `192.168.1.100` | IP address | Filtered out (IP pattern) |
| **TC11** | `aws_lambda_function.filter_test` | `admin@example.com` | Email address | Filtered out (email pattern) |
| **TC12** | `aws_lambda_function.filter_test` | `very-long-string...` | Length > 100 | Filtered out (too long) |
| **TC15** | `aws_lambda_function.self_ref_test` | `self-ref-test` | Self-reference | Prevented (self-loop) |

**Total Expected Non-Matches: 7 cases**

## Cách chạy Test

### 1. Chạy Phase 1 (Preprocessing)

```bash
cd /home/thangdd/repos/TerrARA
./phase1_quick_start.sh
# Hoặc chạy từng bước:
python3 phase1_load_graph.py <json_file> implicit_resolver_step_2
python3 phase1_enrich_graph.py implicit_resolver_step_2
python3 phase1_exact_matching.py implicit_resolver_step_2
```

### 2. Kiểm tra kết quả

#### Option A: Query Graph Database

```bash
python3 phase1_query_graph.py implicit_resolver_step_2
```

#### Option B: Memgraph Lab (Web UI)

1. Mở `http://localhost:3000`
2. Chạy query:
```cypher
MATCH (source)-[r:REF]->(target)
WHERE r.method = 'implicit_exact_match'
RETURN source.type, source.name, target.type, target.name, r.method
ORDER BY source.type, source.name
```

### 3. So sánh kết quả

**Expected Results:**

```
✓ Lambda processor → SQS order_queue (TC1)
✓ Lambda processor → S3 data_bucket (TC2)
✓ Lambda processor → S3 data_bucket (TC3)
✓ EC2 web_server → Security Group web_sg (TC4)
✓ RDS app_db → Subnet private_subnet (TC5)
✓ EC2 multi_sg_server → Security Group sg1 (TC6)
✓ EC2 multi_sg_server → Security Group sg2 (TC6)
✓ Lambda case_test → RDS payment_db (TC13)
✓ Lambda case_test → RDS payment_db (TC14)
✓ Lambda nested_test → RDS payment_db (TC16)
✓ Lambda nested_test → SQS order_queue (TC16)
✓ Lambda nested_test → S3 data_bucket (TC16)

✗ Lambda filter_test → (no matches for TC7-12)
✗ Lambda self_ref_test → (no self-loop for TC15)
```

## Metrics để đánh giá

### Precision (Độ chính xác)
```
Precision = True Positives / (True Positives + False Positives)
```

- **True Positives**: Số links đúng được tạo (Expected Matches)
- **False Positives**: Số links sai được tạo (không nên match nhưng lại match)

**Target**: Precision > 95%

### Recall (Độ bao phủ)
```
Recall = True Positives / (True Positives + False Negatives)
```

- **True Positives**: Số links đúng được tạo
- **False Negatives**: Số links đúng nhưng bị bỏ sót

**Target**: Recall > 90%

### False Positive Rate
```
FPR = False Positives / (False Positives + True Negatives)
```

- **False Positives**: Links sai được tạo
- **True Negatives**: Cases đúng không match (TC7-12, TC15)

**Target**: FPR < 5%

## Test Cases Chi Tiết

### TC1: Variable Resolution + Physical ID Match
- **Input**: `QUEUE_TARGET = var.target_queue_name`
- **Step 1 Output**: `"order-processing-queue-production"`
- **Step 2**: Match với Physical ID của `aws_sqs_queue.order_queue`
- **Expected**: ✓ Match

### TC2: Logical ID Match
- **Input**: `BUCKET_LOGICAL_REF = "data_bucket"`
- **Step 2**: Match với base name `"data_bucket"` của `aws_s3_bucket.data_bucket`
- **Expected**: ✓ Match

### TC3: Variable Interpolation → Physical ID
- **Input**: `DIRECT_PHYSICAL_REF = "${var.project_code}-data-storage"`
- **Step 1 Output**: `"alpha-data-storage"`
- **Step 2**: Match với Physical ID của `aws_s3_bucket.data_bucket`
- **Expected**: ✓ Match

### TC4: Hardcoded Security Group Name
- **Input**: `vpc_security_group_ids = ["web-sg"]`
- **Step 2**: Match với name `"web-sg"` của `aws_security_group.web_sg`
- **Expected**: ✓ Match

### TC5: Hardcoded Subnet Name (from tags)
- **Input**: `subnet_id = "private-subnet"`
- **Step 2**: Match với tags.Name `"private-subnet"` của `aws_subnet.private_subnet`
- **Expected**: ✓ Match (nếu Step 2 hỗ trợ tags.Name)

### TC6: Multiple Matches
- **Input**: `vpc_security_group_ids = ["web-sg", "web-sg-alt"]`
- **Step 2**: Match cả 2 Security Groups
- **Expected**: ✓ 2 Matches

### TC7-12: False Positive Prevention
- **TC7**: ARN → Filtered out
- **TC8**: URL → Filtered out
- **TC9**: Empty string → Filtered out
- **TC10**: IP address → Filtered out
- **TC11**: Email → Filtered out
- **TC12**: Long string (>100 chars) → Filtered out
- **Expected**: ✗ No matches

### TC13-14: Case Sensitivity
- **TC13**: `"payment-db"` (lowercase) → Match với `payment_db` (case-insensitive)
- **TC14**: `"PAYMENT-DB"` (uppercase) → Match với `payment_db` (case-insensitive)
- **Expected**: ✓ Match (nếu case_sensitive=False)

### TC15: Self-Reference Prevention
- **Input**: Lambda references its own `function_name`
- **Step 2**: Should detect self-reference and skip
- **Expected**: ✗ No match (self-loop prevention)

### TC16: Nested Structure Extraction
- **Input**: JSON string với nested objects/arrays
- **Step 2**: Should extract strings from nested structures
- **Expected**: ✓ Match strings inside nested structures

## Kết quả mong đợi

Sau khi chạy Step 2, bạn nên thấy:

1. **13 implicit links được tạo** (từ TC1-6, TC13-14, TC16)
2. **0 false positive links** (TC7-12, TC15 không tạo link)
3. **Edge property**: `r.method = 'implicit_exact_match'`

## Troubleshooting

### Nếu thiếu links:
- Kiểm tra Step 1 (Taint Analysis) đã chạy chưa
- Kiểm tra `taint_resolved_properties` có được populate không
- Kiểm tra Symbol Table có đầy đủ resources không

### Nếu có false positives:
- Kiểm tra filter logic trong `extract_string_values()`
- Kiểm tra self-loop prevention trong `create_implicit_links()`

### Nếu nested structures không match:
- Kiểm tra `extract_recursive()` có xử lý nested structures không
- Kiểm tra JSON parsing trong Step 1
