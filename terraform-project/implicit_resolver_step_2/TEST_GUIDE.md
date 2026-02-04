# Hướng dẫn Test Step 2 với Implicit Resolver

## Quick Start

### 1. Chạy test script tự động

```bash
cd /home/thangdd/repos/TerrARA
python3 test_implicit_impact.py implicit_resolver_step_2
```

Script sẽ:
1. Chạy TerrARA **KHÔNG** có implicit resolver → Đếm threats
2. Chạy TerrARA **CÓ** implicit resolver → Đếm threats
3. So sánh và báo cáo kết quả

### 2. Xem kết quả

Script sẽ in ra console báo cáo so sánh và lưu vào:
- `test_output/comparison_report.json`

## Expected Results

### Với project `implicit_resolver_step_2`:

**Expected Matches (13 links):**
- Lambda processor → SQS order_queue (TC1)
- Lambda processor → S3 data_bucket (TC2, TC3)
- EC2 web_server → Security Group web_sg (TC4)
- RDS app_db → Subnet private_subnet (TC5)
- EC2 multi_sg_server → Security Groups sg1, sg2 (TC6)
- Lambda case_test → RDS payment_db (TC13-14)
- Lambda nested_test → RDS, SQS, S3 (TC16)

**Expected Non-Matches (7 cases):**
- ARN, URL, Empty, IP, Email, Long string (TC7-12)
- Self-reference (TC15)

## Manual Testing

Nếu muốn test thủ công từng bước:

### Step 1: Load graph (không có implicit resolver)

```bash
# Chạy Phase 1
./phase1_quick_start.sh

# Hoặc từng bước:
python3 phase1_load_graph.py <json_file> implicit_resolver_step_2
python3 phase1_enrich_graph.py implicit_resolver_step_2
# KHÔNG chạy phase1_exact_matching.py ở đây
```

### Step 2: Chạy main.py (không có implicit resolver)

```bash
ENABLE_IMPLICIT_RESOLVER=false python3 main.py implicit_resolver_step_2
```

### Step 3: Chạy với implicit resolver

```bash
ENABLE_IMPLICIT_RESOLVER=true python3 main.py implicit_resolver_step_2
```

### Step 4: So sánh

So sánh số threats trong:
- `output/without_implicit/output.csv`
- `output/with_implicit/output.csv`

## Kiểm tra Links trong Graph

```bash
python3 phase1_query_graph.py implicit_resolver_step_2
```

Hoặc trong Memgraph Lab (`http://localhost:3000`):

```cypher
// Xem tất cả implicit links
MATCH (source)-[r:REF]->(target)
WHERE r.method = 'implicit_exact_match'
RETURN source.type, source.name, target.type, target.name, r.method

// Đếm links theo method
MATCH ()-[r:REF]->()
WHERE r.method IS NOT NULL
RETURN r.method, count(*) as count
ORDER BY count DESC
```
