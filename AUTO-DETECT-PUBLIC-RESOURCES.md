# Auto-Detect Public Resources - Giải Pháp Tự Động Phát Hiện Public Resources

## Tổng Quan

Module này tự động phát hiện và đánh dấu các resources (EC2, RDS) có public access thông qua Security Group với ingress rules cho phép `0.0.0.0/0`.

## Vấn Đề

### 1. Thiết Kế Pattern SPARTA

Các pattern threat trong SPARTA yêu cầu **direct flow** từ `RemoteUser` đến resource để phát hiện threats:

- **VirtualMachine (EC2)**: 
  - Pattern_58: "Information Disclosure: Network Scanning"
  - Pattern_65: "Tampering: Remote Code Execution"
  - Pattern_68: "Elevation of Privilege: Privilege Escalation"

- **Database (RDS)**:
  - Pattern_0_0_2: "Tampering: Unauthorized Modification"
  - Pattern_0_1_2: "Information Disclosure: Sensitive Data Leakage"
  - Pattern_0_2_2: "Denial of Service against Data Store"
  - Pattern_0_3_2: "Repudiation: Attacking the Logs"

Tất cả đều yêu cầu:
```pattern
DataFlow.sender(df, ee);  // User là sender
DataFlow.recipient(df, p); // EC2/RDS là recipient
```

### 2. Thực Tế AWS

Trong thực tế AWS:
- **EC2** luôn phải có Security Group (bắt buộc)
- **RDS** luôn phải có Security Group (bắt buộc)
- User không thể truy cập trực tiếp EC2/RDS
- Flow thực tế: `User → Security Group → EC2/RDS`

### 3. Vấn Đề Thiết Kế

- EC2/RDS không có `can_public: true` trong `aws_annotation.yaml`
- User chỉ kết nối với `publicNodes` (resources có `can_public: true`)
- Không có direct flow `User → EC2/RDS` được tạo
- → **Các pattern threat cho EC2/RDS không được kích hoạt**

## Giải Pháp

### Tự Động Phát Hiện Public Resources

Module `utils/auto_detect_public_resources.py` tự động:

1. **Parse Terraform files** để lấy Security Group properties
2. **Kiểm tra ingress rules** của Security Group
3. **Phát hiện public access** nếu có `cidr_blocks = ["0.0.0.0/0"]`
4. **Tìm EC2/RDS connected** đến Security Group đó qua graph database
5. **Tự động mark** EC2/RDS là `publicNode` → tạo direct flow `User → EC2/RDS`

### Kiến Trúc

```
┌─────────────────────────────────────────────────────────┐
│  Terraform Project                                       │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ Security Group   │  │ EC2 Instance      │            │
│  │ ingress:         │  │ vpc_security_     │            │
│  │   cidr_blocks:   │  │   group_ids:     │            │
│  │   ["0.0.0.0/0"]  │←─│   [sg.id]        │            │
│  └──────────────────┘  └──────────────────┘            │
└─────────────────────────────────────────────────────────┘
         │                           │
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│  Parse Terraform Files                                   │
│  - Extract Security Group properties                    │
│  - Check ingress rules                                  │
└─────────────────────────────────────────────────────────┘
         │                           │
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│  Graph Database Query                                    │
│  - Find Security Groups with public ingress             │
│  - Find EC2/RDS connected to Security Groups            │
└─────────────────────────────────────────────────────────┘
         │                           │
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│  Auto-Mark as Public                                     │
│  - diag.AddPublicNode(ec2_node)                         │
│  - Creates User → EC2 direct flow                        │
└─────────────────────────────────────────────────────────┘
```

## Cách Sử Dụng

### Tự Động Kích Hoạt

Module được tích hợp tự động vào `main.py`. Không cần cấu hình thêm.

```python
# Trong main.py (line 177-195)
auto_public_ids = auto_detect_public_resources(in_path, pathID)
for resource_id in auto_public_ids:
    if resource_id in COMPONENT_ID_NODE:
        resource_node = COMPONENT_ID_NODE[resource_id]
        diag.AddPublicNode(resource_node)
```

### Ví Dụ

**Terraform Configuration:**
```terraform
resource "aws_security_group" "allow_ssh" {
  name        = "allow_ssh"
  description = "Allow SSH inbound traffic"
  vpc_id      = aws_vpc.main_vpc.id

  ingress {
    description = "SSH from Internet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # ← Public access
  }
}

resource "aws_instance" "app_server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.public_subnet.id
  vpc_security_group_ids = [aws_security_group.allow_ssh.id] # ← Connected to public SG
}
```

**Kết Quả:**
- Security Group `allow_ssh` có ingress rule `0.0.0.0/0` → **Public**
- EC2 `app_server` connected đến Security Group → **Tự động mark là public**
- Direct flow `User → EC2` được tạo
- SPARTA patterns có thể match và phát hiện threats

## API Reference

### `auto_detect_public_resources(project_path: str, pathID: str) -> Set[str]`

Tự động phát hiện và trả về danh sách resource IDs cần được mark là public.

**Parameters:**
- `project_path`: Path to Terraform project directory
- `pathID`: Path ID của project trong graph database

**Returns:**
- `Set[str]`: Set of resource node IDs (as strings) cần được mark là public

**Example:**
```python
from utils.auto_detect_public_resources import auto_detect_public_resources

public_ids = auto_detect_public_resources("/path/to/terraform/project", pathID)
# Returns: {'123', '456', '789'}  # Node IDs của EC2/RDS có public access
```

### `has_public_ingress(ingress_rules: List[Dict[str, Any]]) -> bool`

Kiểm tra Security Group có ingress rule cho phép `0.0.0.0/0` không.

**Parameters:**
- `ingress_rules`: List of ingress rule dictionaries

**Returns:**
- `bool`: True nếu có ít nhất một rule cho phép `0.0.0.0/0`

### `find_resources_connected_to_sg(pathID: str, sg_node_id: str, resource_types: List[str]) -> List[Dict[str, Any]]`

Tìm các resources (EC2, RDS) connected đến Security Group.

**Parameters:**
- `pathID`: Path ID của project
- `sg_node_id`: Node ID của Security Group trong graph
- `resource_types`: List of resource types to find (e.g., `["aws_instance", "aws_db_instance"]`)

**Returns:**
- `List[Dict[str, Any]]`: List of resource records với `id`, `group`, `general_name`, `tfname`

## Logging

Module sử dụng Python logging để log các hoạt động:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

**Log Messages:**
- `INFO`: Found public Security Group, found connected resources, auto-marked resources
- `WARNING`: Error querying resources, resource not found
- `DEBUG`: Security Group not found in parsed resources

## Limitations

### 1. Chỉ Hoạt Động Với Explicit Links

Module chỉ phát hiện resources có **explicit links** đến Security Group:
- ✅ `vpc_security_group_ids = [aws_security_group.allow_ssh.id]`
- ❌ `vpc_security_group_ids = ["allow_ssh"]` (implicit link)

### 2. Chỉ Parse Root-Level Files

Module chỉ parse root-level `.tf` files. Resources trong modules có thể không được phát hiện nếu không có explicit links.

### 3. Không Hỗ Trợ Dynamic Values

Module không resolve dynamic values như:
- Variables: `cidr_blocks = var.public_cidr`
- Functions: `cidr_blocks = [cidrsubnet(...)]`

Chỉ phát hiện literal values: `cidr_blocks = ["0.0.0.0/0"]`

## Testing

### Test Case 1: EC2 với Public Security Group

**Input:**
```terraform
resource "aws_security_group" "allow_ssh" {
  ingress {
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app_server" {
  vpc_security_group_ids = [aws_security_group.allow_ssh.id]
}
```

**Expected Output:**
- EC2 `app_server` được mark là public
- Direct flow `User → EC2` được tạo
- Threats cho EC2 được phát hiện

### Test Case 2: RDS với Public Security Group

**Input:**
```terraform
resource "aws_security_group" "rds_sg" {
  ingress {
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main_db" {
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}
```

**Expected Output:**
- RDS `main_db` được mark là public
- Direct flow `User → RDS` được tạo
- Threats cho RDS được phát hiện

### Test Case 3: Security Group Không Public

**Input:**
```terraform
resource "aws_security_group" "private_sg" {
  ingress {
    cidr_blocks = ["10.0.0.0/16"]  # Private CIDR
  }
}

resource "aws_instance" "app_server" {
  vpc_security_group_ids = [aws_security_group.private_sg.id]
}
```

**Expected Output:**
- EC2 `app_server` **KHÔNG** được mark là public
- Không có direct flow `User → EC2`
- Threats cho EC2 **KHÔNG** được phát hiện

## Tương Lai

### Cải Thiện Có Thể

1. **Hỗ Trợ Implicit Links**: Phát hiện resources với hardcoded Security Group names
2. **Resolve Dynamic Values**: Sử dụng taint analysis để resolve variables
3. **Parse Module Files**: Mở rộng để parse resources trong modules
4. **Hỗ Trợ IPv6**: Phát hiện `::/0` trong `ipv6_cidr_blocks`

## Tài Liệu Liên Quan

- [SPARTA Threat Catalog](./sparta_utils/IACNewCatalog_v2.sparta)
- [AWS Annotation Configuration](./input/aws_annotation.yaml)
- [Main Pipeline](./main.py)
- [Terraform Parser](./tfparser/parse_tf_properties.py)

## Tác Giả

Giải pháp được implement để giải quyết vấn đề thiết kế trong SPARTA patterns yêu cầu direct flow từ User đến EC2/RDS, trong khi thực tế AWS luôn đi qua Security Group.
