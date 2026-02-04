# Step 3: Boundary-aware Substring Matching

## Overview

Step 3 is the critical step of the 5-step pipeline for resolving implicit dependencies in Terraform. It performs **boundary-aware substring matching** between complex strings (ARNs, URLs, Connection Strings) and resource names to create missing dependency links.

**Role in Pipeline**: Handles complex identifier-based dependencies that Step 2 (Exact Matching) cannot process

## Problem Statement

### Complex String References

Developers often reference resources through complex identifiers rather than simple names:

- **ARNs**: `arn:aws:s3:::finance-data-bucket`
- **URLs**: `https://sqs.us-east-1.amazonaws.com/123456789/queue-name`
- **Connection Strings**: `postgresql://host:5432/dbname`
- **Domain Names**: `api.example.com`

**Example Problem**:
```terraform
# S3 Bucket
resource "aws_s3_bucket" "finance_data" {
  bucket = "finance-data-bucket"
}

# Lambda Function (missing explicit reference)
resource "aws_lambda_function" "processor" {
  environment {
    variables = {
      BUCKET_ARN = "arn:aws:s3:::finance-data-bucket"  # ← Complex string, not ${aws_s3_bucket.finance_data.arn}
    }
  }
}
```

**Result**: Terraform graph shows no connection between Lambda and S3 Bucket, even though the ARN contains the bucket name.

### The Boundary Problem

Simple substring matching would create false positives:
- `"user"` would match in `"superuser"` ❌
- `"db"` would match in `"mydb"` ❌

We need to ensure the substring appears with **valid boundary characters** to avoid matching words within words.

### What Step 3 Solves

- **ARN References**: Matches resource names within ARN strings
- **URL References**: Matches resource names within URL paths
- **Connection Strings**: Matches database names in JDBC/connection strings
- **Domain Names**: Matches service names in domain names
- **Boundary Validation**: Prevents false positives from word-within-word matches

## Algorithm: Boundary-aware Substring Matching

The algorithm uses a **Substring Search with Boundary Validation** approach:

1. **Build Symbol Table**: Create mapping of all resource names → resource metadata (same as Step 2)
2. **Extract Complex Strings**: Get ARNs, URLs, connection strings from `taint_resolved_properties`
3. **Substring Search**: For each complex string, check if any resource name appears as a substring
4. **Boundary Validation**: Verify that substring has valid boundary characters (not letters/digits)
5. **Create Links**: Create `REF` edges for valid matches

### Detailed Steps

#### Step 1: Build Symbol Table
Query all resources in the graph and build a dictionary mapping:
- **Full names**: `"aws_s3_bucket.finance_data"` → resource metadata
- **Base names**: `"finance_data"` → resource metadata

#### Step 2: Extract Complex Strings
Recursively extract complex strings from `taint_resolved_properties` JSON:
- **ARNs**: Strings starting with `arn:`
- **URLs**: Strings starting with `http://` or `https://`
- **Connection Strings**: Strings matching `jdbc://`, `postgresql://`, `mysql://`, etc.
- **SQS URLs**: URLs containing `sqs.` and `amazonaws.com`
- **Domain Names**: Strings with `.` that are not IP addresses
- **Long Strings**: Strings longer than 50 characters (may contain identifiers)

#### Step 3: Boundary-aware Matching
For each complex string and each resource name:
1. Find substring position using case-insensitive search
2. Check character **before** substring:
   - Valid: `:`, `/`, `.`, `@`, `-`, `"`, or start of string
   - Invalid: letters (a-z, A-Z) or digits (0-9)
3. Check character **after** substring:
   - Valid: `:`, `/`, `.`, `@`, `-`, `"`, or end of string
   - Invalid: letters (a-z, A-Z) or digits (0-9)
4. If both boundaries are valid → **MATCH**

#### Step 4: Create REF Edges
For each match:
- Create `REF` edge: `(source_resource) -[:REF]-> (target_resource)`
- Use `MERGE` to avoid duplicates
- Log created links

## Implementation Details

### Class: `BoundaryAwareMatcher`

**Location**: `implicit_dependency_resolver/boundary_aware_matching.py`

**Initialization**:
```python
matcher = BoundaryAwareMatcher(path_id, case_sensitive=False)
```

### Key Methods

1. **`build_symbol_table()` → Dict**
   - Queries all resources from graph
   - Builds mapping: `name → {node_id, resource_type, full_name, base_name}`
   - Handles both `name` and `resource_name` properties
   - Returns symbol table dictionary

2. **`extract_complex_strings(resolved_properties)` → List[str]**
   - Recursively extracts complex strings from nested structures
   - Filters IN (opposite of Step 2):
     - ARNs (`arn:aws:...`)
     - URLs (`http://`, `https://`)
     - Connection strings (`jdbc:`, `postgresql://`, etc.)
     - SQS URLs
     - Domain names
     - Long strings (>50 chars)
   - Returns list of candidate strings

3. **`is_valid_boundary(char)` → bool**
   - Checks if character is valid boundary
   - Valid: `:`, `/`, `.`, `@`, `-`, `"`, or `None` (start/end)
   - Invalid: letters or digits

4. **`check_boundary_match(source_string, target_name)` → bool**
   - Finds all occurrences of `target_name` in `source_string`
   - Validates boundaries for each occurrence
   - Returns `True` if any occurrence has valid boundaries

5. **`find_matching_resources(source_string, symbol_table)` → List[Dict]**
   - Checks each resource name against `source_string`
   - Uses boundary-aware substring matching
   - Returns list of matching resource records

6. **`create_implicit_links(source_id, target_id)` → bool**
   - Creates `REF` edge between resources
   - Checks for existing edges to avoid duplicates
   - Returns `True` if edge was created

7. **`run()` → int**
   - Main execution method
   - Orchestrates all steps
   - Returns count of links created

### Boundary Validation Logic

```python
VALID_BOUNDARY_CHARS = {':', '/', '.', '@', '-', '"'}
INVALID_BOUNDARY_CHARS = set(string.ascii_letters + string.digits)

def check_boundary_match(source: str, target: str) -> bool:
    # Case-insensitive search
    source_lower = source.lower()
    target_lower = target.lower()
    
    # Find all occurrences
    start_pos = source_lower.find(target_lower)
    while start_pos != -1:
        end_pos = start_pos + len(target)
        
        # Check character before
        char_before = source[start_pos - 1] if start_pos > 0 else None
        # Check character after
        char_after = source[end_pos] if end_pos < len(source) else None
        
        # Validate boundaries
        if is_valid_boundary(char_before) and is_valid_boundary(char_after):
            return True
        
        # Find next occurrence
        start_pos = source_lower.find(target_lower, start_pos + 1)
    
    return False
```

### String Extraction Logic

Complex strings are extracted from `taint_resolved_properties` JSON:
```json
{
    "bucket_arn": "arn:aws:s3:::finance-data-bucket",
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789/queue-name",
    "db_connection": "postgresql://host:5432/dbname"
}
```

Extracted strings: `["arn:aws:s3:::finance-data-bucket", "https://sqs.us-east-1.amazonaws.com/123456789/queue-name", "postgresql://host:5432/dbname"]`

## Data Flow

### Input
- **Graph**: Resources with `taint_resolved_properties` property (from Step 1)
- **Symbol Table**: All resource names in the project

### Processing
1. Parse `taint_resolved_properties` JSON
2. Extract complex strings (ARNs, URLs, etc.)
3. For each complex string:
   - Search for each resource name as substring
   - Validate boundaries
   - Collect matches
4. Create `REF` edges for matches

### Output
- **REF Edges**: New relationships between resources
- **Count**: Number of implicit links created

## Usage

### Basic Usage
```python
from implicit_dependency_resolver.boundary_aware_matching import BoundaryAwareMatcher
from utils.n4j_helper import GetPathID

project_path = "/path/to/terraform/project"
path_id = GetPathID(project_path)

matcher = BoundaryAwareMatcher(path_id, case_sensitive=False)
links_created = matcher.run()
print(f"Created {links_created} implicit links")
```

### Case-Sensitive Matching
```python
matcher = BoundaryAwareMatcher(path_id, case_sensitive=True)
links_created = matcher.run()
```

### Integration in Pipeline
Step 3 should be called after Step 2:
```python
# After Step 2 (Exact Matching)
from implicit_dependency_resolver.boundary_aware_matching import BoundaryAwareMatcher

matcher = BoundaryAwareMatcher(path_id)
links_created = matcher.run()
logger.info(f"Boundary-aware Matching completed: {links_created} links created")
```

## Examples

### Example 1: ARN Matching

**Terraform Code**:
```terraform
resource "aws_s3_bucket" "finance_data" {
  bucket = "finance-data-bucket"
}

resource "aws_lambda_function" "processor" {
  environment {
    variables = {
      BUCKET_ARN = "arn:aws:s3:::finance-data-bucket"  # Hardcoded ARN
    }
  }
}
```

**Step 1 Output** (on Lambda resource):
```json
{
  "taint_resolved_properties": {
    "environment": {
      "variables": {
        "BUCKET_ARN": "arn:aws:s3:::finance-data-bucket"
      }
    }
  }
}
```

**Step 3 Processing**:
1. Extract complex string: `"arn:aws:s3:::finance-data-bucket"`
2. Search for `"finance-data-bucket"` in ARN → Found at position 15
3. Check boundary before: `:` (valid ✓)
4. Check boundary after: End of string (valid ✓)
5. Create edge: `(aws_lambda_function.processor) -[:REF]-> (aws_s3_bucket.finance_data)`

**Result**: Lambda now has explicit link to S3 Bucket in graph.

### Example 2: URL Matching

**Terraform Code**:
```terraform
resource "aws_sqs_queue" "task_queue" {
  name = "task-queue"
}

resource "aws_lambda_function" "worker" {
  environment {
    variables = {
      QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/task-queue"
    }
  }
}
```

**Step 3 Processing**:
1. Extract complex string: `"https://sqs.us-east-1.amazonaws.com/123456789/task-queue"`
2. Search for `"task-queue"` in URL → Found at position 52
3. Check boundary before: `/` (valid ✓)
4. Check boundary after: End of string (valid ✓)
5. Create edge: `(aws_lambda_function.worker) -[:REF]-> (aws_sqs_queue.task_queue)`

### Example 3: Boundary Validation (False Positive Prevention)

**Terraform Code**:
```terraform
resource "aws_db_instance" "user_db" {
  db_name = "user-db"
}

resource "aws_db_instance" "superuser_db" {
  db_name = "superuser-db"
}

resource "aws_lambda_function" "api" {
  environment {
    variables = {
      DB_CONNECTION = "postgresql://host:5432/superuser-db"
    }
  }
}
```

**Step 3 Processing**:
1. Extract complex string: `"postgresql://host:5432/superuser-db"`
2. Search for `"user-db"` in connection string:
   - Found at position 28 (within `"superuser-db"`)
   - Check boundary before: `r` (letter, invalid ✗)
   - **No match** (prevents false positive)
3. Search for `"superuser-db"` in connection string:
   - Found at position 23
   - Check boundary before: `/` (valid ✓)
   - Check boundary after: End of string (valid ✓)
   - **Match** ✓
4. Create edge: `(aws_lambda_function.api) -[:REF]-> (aws_db_instance.superuser_db)`

**Result**: Correctly matches `superuser-db` without false positive for `user-db`.

### Example 4: Connection String Matching

**Terraform Code**:
```terraform
resource "aws_db_instance" "payment_db" {
  db_name = "payment-db"
}

resource "aws_lambda_function" "processor" {
  environment {
    variables = {
      DATABASE_URL = "postgresql://user:pass@host:5432/payment-db"
    }
  }
}
```

**Step 3 Processing**:
1. Extract complex string: `"postgresql://user:pass@host:5432/payment-db"`
2. Search for `"payment-db"` → Found at position 40
3. Check boundary before: `/` (valid ✓)
4. Check boundary after: End of string (valid ✓)
5. Create edge: `(aws_lambda_function.processor) -[:REF]-> (aws_db_instance.payment_db)`

## Limitations

### What Step 3 Does NOT Handle

1. **Exact Matches**: Simple strings that exactly match (Step 2 handles these)
   ```terraform
   # Step 3 won't process this (Step 2 already handled it):
   security_groups = ["web-sg"]
   ```

2. **Fuzzy Matches**: Typos or naming variations (Step 4 handles these)
   ```terraform
   # Won't match:
   resource_name = "web-sg"
   property_value = "arn:aws:ec2:::web_sg"  # Different separator
   ```

3. **Dynamic Names**: Names with random suffixes (Step 4 handles these)
   ```terraform
   # Won't match:
   resource_name = "app-server-x9z"
   property_value = "arn:aws:ec2:::app-server"
   ```

4. **Nested Interpolation**: Complex variable interpolation
   ```terraform
   # Cannot resolve:
   arn = "arn:aws:s3:::${var.env}-${var.app}-bucket"
   ```

### Edge Cases

- **Empty Symbol Table**: No resources found → returns 0 links
- **No Complex Strings**: Resources without ARNs/URLs → skipped
- **Self-References**: Prevents creating self-loops
- **Duplicate Edges**: Uses `MERGE` to avoid duplicates
- **Case Sensitivity**: Configurable via constructor parameter
- **Multiple Matches**: Returns all valid matches (may create multiple edges)

## Configuration Options

### Case Sensitivity

**Default**: Case-insensitive matching (more forgiving)
```python
matcher = BoundaryAwareMatcher(path_id, case_sensitive=False)
```

**Strict Mode**: Case-sensitive matching
```python
matcher = BoundaryAwareMatcher(path_id, case_sensitive=True)
```

## Performance Considerations

- **Symbol Table**: Built once per run (O(n) where n = number of resources)
- **String Extraction**: Recursive traversal of JSON (O(m) where m = property count)
- **Substring Search**: O(n*m*k) where:
  - n = number of resources
  - m = number of complex strings
  - k = average length of resource names
- **Boundary Validation**: O(1) per occurrence
- **Edge Creation**: MERGE operation (O(1) average case)

**Total Complexity**: O(n + m + n*m*k) where n = resources, m = total properties, k = average name length

**Optimization**: Early filtering of non-complex strings reduces m significantly.

## Boundary Validation Rules

### Valid Boundary Characters
- `:` (colon) - Common in ARNs, URLs
- `/` (slash) - Common in URLs, paths
- `.` (dot) - Common in domain names, ARNs
- `@` (at sign) - Common in connection strings
- `-` (hyphen) - Common in resource names
- `"` (quote) - String delimiters
- `None` - Start or end of string

### Invalid Boundary Characters
- **Letters** (a-z, A-Z) - Would match words within words
- **Digits** (0-9) - Would match numbers within numbers

### Examples

| Source String | Target Name | Boundary Before | Boundary After | Match? |
|--------------|-------------|------------------|----------------|--------|
| `arn:aws:s3:::bucket-name` | `bucket-name` | `:` | End | ✓ |
| `https://sqs.../queue-name` | `queue-name` | `/` | End | ✓ |
| `postgresql://host/dbname` | `dbname` | `/` | End | ✓ |
| `superuser-db` | `user-db` | `r` (letter) | `-` | ✗ |
| `mydb123` | `db` | `y` (letter) | `1` (digit) | ✗ |
| `api.example.com` | `example` | `.` | `.` | ✓ |

## Next Steps

After Step 3 completes, proceed to:
- **Step 4: Fuzzy & Heuristic Matching** - Handles typos and naming variations
- **Step 5: Ghost Node Creation** - Creates external entity nodes for unmatched strings

## References

- **Algorithm**: Substring Search with Boundary Validation
- **Implementation**: `implicit_dependency_resolver/boundary_aware_matching.py`
- **Dependencies**: Requires Step 1 (`taint_resolved_properties`) to be completed first
- **Related**: Step 2 (Exact Matching) handles simple strings, Step 3 handles complex strings
