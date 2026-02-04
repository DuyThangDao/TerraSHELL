# Step 2: Exact Matching

## Overview

Step 2 is the "Happy Path" of the 5-step pipeline for resolving implicit dependencies in Terraform. It performs **exact string matching** between resolved property values (from Step 1) and resource names to create missing dependency links.

**Role in Pipeline**: Primary matching step for simple identifier-based dependencies

## Problem Statement

### Missing Implicit Dependencies

Developers sometimes use hardcoded strings that exactly match resource names, but forget to use Terraform's reference syntax (`${...}`). This causes Terraform's dependency graph to miss the connection.

**Example Problem**:
```terraform
# Security Group
resource "aws_security_group" "web_sg" {
  name = "web-sg"
}

# EC2 Instance (missing explicit reference)
resource "aws_instance" "app" {
  vpc_security_group_ids = ["web-sg"]  # ← Hardcoded string, not ${aws_security_group.web_sg.id}
}
```

**Result**: Terraform graph shows no connection between EC2 and Security Group, even though they are related.

### What Step 2 Solves

- **Hardcoded Name References**: Matches strings like `"web-sg"` against resource names
- **Exact Matches**: Handles cases where string exactly matches resource name
- **Case Variations**: Supports both case-sensitive and case-insensitive matching
- **Missing Links**: Creates `REF` edges between resources that should be connected

## Algorithm: Symbol Table Matching

The algorithm uses a **Symbol Table** approach:

1. **Build Symbol Table**: Create mapping of all resource names → resource metadata
2. **Extract Strings**: Get resolved string values from `taint_resolved_properties` (Step 1 output)
3. **Match Strings**: Compare extracted strings against symbol table
4. **Create Links**: Create `REF` edges for exact matches

### Detailed Steps

#### Step 1: Build Symbol Table
Query all resources in the graph and build a dictionary mapping:
- **Full names**: `"aws_security_group.web_sg"` → resource metadata
- **Base names**: `"web_sg"` → resource metadata

This allows matching both full resource identifiers and simple names.

#### Step 2: Query Resources with Resolved Properties
Find all resources that have `taint_resolved_properties` (populated by Step 1).

#### Step 3: Extract String Values
Recursively extract all string values from `taint_resolved_properties` JSON:
- Handle nested dictionaries
- Handle lists
- Filter out complex strings (ARNs, URLs) - these are handled by Step 3

#### Step 4: Match Against Symbol Table
For each extracted string:
- Normalize for case-insensitive matching (if configured)
- Look up in symbol table
- Find matching resources

#### Step 5: Create REF Edges
For each match:
- Create `REF` edge: `(source_resource) -[:REF]-> (target_resource)`
- Use `MERGE` to avoid duplicates
- Log created links

## Implementation Details

### Class: `ExactMatcher`

**Location**: `implicit_dependency_resolver/exact_matching.py`

**Initialization**:
```python
matcher = ExactMatcher(path_id, case_sensitive=False)
```

### Key Methods

1. **`build_symbol_table()` → Dict**
   - Queries all resources from graph
   - Builds mapping: `name → {node_id, resource_type, full_name, base_name}`
   - Handles both `name` and `resource_name` properties
   - Returns symbol table dictionary

2. **`extract_string_values(resolved_properties)` → List[str]**
   - Recursively extracts strings from nested structures
   - Filters out:
     - Empty strings
     - ARNs (`arn:aws:...`)
     - URLs (`http://`, `https://`)
     - Email addresses
     - IP addresses
     - Very long strings (>100 chars)
   - Returns list of candidate strings

3. **`find_matching_resources(source_string, symbol_table)` → List[Dict]**
   - Matches `source_string` against symbol table
   - Supports case-sensitive and case-insensitive matching
   - Returns list of matching resource records

4. **`create_implicit_links(source_id, target_id)` → bool**
   - Creates `REF` edge between resources
   - Checks for existing edges to avoid duplicates
   - Returns `True` if edge was created

5. **`run()` → int**
   - Main execution method
   - Orchestrates all steps
   - Returns count of links created

### Symbol Table Structure

```python
{
    "aws_security_group.web_sg": {
        "node_id": 123,
        "resource_type": "aws_security_group",
        "full_name": "aws_security_group.web_sg",
        "base_name": "web_sg"
    },
    "web_sg": {  # Also stored as base name
        "node_id": 123,
        "resource_type": "aws_security_group",
        "full_name": "aws_security_group.web_sg",
        "base_name": "web_sg"
    }
}
```

### String Extraction Logic

Strings are extracted from `taint_resolved_properties` JSON:
```json
{
    "vpc_security_group_ids": ["web-sg", "db-sg"],
    "subnet_id": "private-subnet",
    "db_name": "payment-db"
}
```

Extracted strings: `["web-sg", "db-sg", "private-subnet", "payment-db"]`

## Data Flow

### Input
- **Graph**: Resources with `taint_resolved_properties` property (from Step 1)
- **Symbol Table**: All resource names in the project

### Processing
1. Parse `taint_resolved_properties` JSON
2. Extract string values
3. Match against symbol table
4. Create `REF` edges

### Output
- **REF Edges**: New relationships between resources
- **Count**: Number of implicit links created

## Usage

### Basic Usage
```python
from implicit_dependency_resolver.exact_matching import ExactMatcher
from utils.n4j_helper import GetPathID

project_path = "/path/to/terraform/project"
path_id = GetPathID(project_path)

matcher = ExactMatcher(path_id, case_sensitive=False)
links_created = matcher.run()
print(f"Created {links_created} implicit links")
```

### Case-Sensitive Matching
```python
matcher = ExactMatcher(path_id, case_sensitive=True)
links_created = matcher.run()
```

### Integration in Pipeline
Step 2 should be called after Step 1:
```python
# After Step 1 (Taint Analysis)
from implicit_dependency_resolver.exact_matching import ExactMatcher

matcher = ExactMatcher(path_id)
links_created = matcher.run()
logger.info(f"Exact Matching completed: {links_created} links created")
```

## Examples

### Example 1: EC2 → Security Group

**Terraform Code**:
```terraform
resource "aws_security_group" "web_sg" {
  name = "web-sg"
}

resource "aws_instance" "app" {
  vpc_security_group_ids = ["web-sg"]  # Hardcoded string
}
```

**Step 1 Output** (on EC2 resource):
```json
{
  "taint_resolved_properties": {
    "vpc_security_group_ids": ["web-sg"]
  }
}
```

**Step 2 Processing**:
1. Extract string: `"web-sg"`
2. Match against symbol table: Found `aws_security_group.web_sg` with base name `"web_sg"`
3. Also try matching `"web-sg"` directly → matches if resource name contains it
4. Create edge: `(aws_instance.app) -[:REF]-> (aws_security_group.web_sg)`

**Result**: EC2 now has explicit link to Security Group in graph.

### Example 2: RDS → Subnet

**Terraform Code**:
```terraform
resource "aws_subnet" "private_subnet" {
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "private-subnet"
  }
}

resource "aws_db_instance" "db" {
  subnet_id = "private-subnet"  # Hardcoded string
}
```

**Step 2 Processing**:
1. Extract string: `"private-subnet"`
2. Match against symbol table: Find resource with name containing `"private-subnet"`
3. Create edge: `(aws_db_instance.db) -[:REF]-> (aws_subnet.private_subnet)`

### Example 3: Multiple Matches

**Terraform Code**:
```terraform
resource "aws_security_group" "sg1" {
  name = "web-sg"
}

resource "aws_security_group" "sg2" {
  name = "web-sg-alt"
}

resource "aws_instance" "app" {
  vpc_security_group_ids = ["web-sg", "web-sg-alt"]
}
```

**Step 2 Processing**:
- Extracts: `["web-sg", "web-sg-alt"]`
- Matches: Both security groups
- Creates: Two `REF` edges from EC2 to both security groups

## Limitations

### What Step 2 Does NOT Handle

1. **Substring Matches**: Only exact matches (Step 3 handles substrings)
   ```terraform
   # This won't match:
   resource_name = "web-sg"
   property_value = "arn:aws:ec2:us-east-1:123456789012:security-group/web-sg"
   ```

2. **Complex Strings**: ARNs, URLs, connection strings (Step 3 handles these)
   ```terraform
   # Step 2 filters these out:
   endpoint = "arn:aws:rds:us-east-1:123456789012:db:payment-db"
   ```

3. **Fuzzy Matches**: Typos or naming variations (Step 4 handles these)
   ```terraform
   # Won't match:
   resource_name = "web-sg"
   property_value = "web_sg"  # Different separator
   ```

4. **Dynamic Names**: Names with random suffixes (Step 4 handles these)
   ```terraform
   # Won't match:
   resource_name = "app-server-x9z"
   property_value = "app-server"
   ```

### Edge Cases

- **Empty Symbol Table**: No resources found → returns 0 links
- **No Resolved Properties**: Resources without Step 1 output → skipped
- **Self-References**: Prevents creating self-loops
- **Duplicate Edges**: Uses `MERGE` to avoid duplicates
- **Case Sensitivity**: Configurable via constructor parameter

## Configuration Options

### Case Sensitivity

**Default**: Case-insensitive matching (more forgiving)
```python
matcher = ExactMatcher(path_id, case_sensitive=False)
```

**Strict Mode**: Case-sensitive matching
```python
matcher = ExactMatcher(path_id, case_sensitive=True)
```

## Performance Considerations

- **Symbol Table**: Built once per run (O(n) where n = number of resources)
- **String Extraction**: Recursive traversal of JSON (O(m) where m = property count)
- **Matching**: Dictionary lookup (O(1) average case)
- **Edge Creation**: MERGE operation (O(1) average case)

**Total Complexity**: O(n + m) where n = resources, m = total properties

## Next Steps

After Step 2 completes, proceed to:
- **Step 3: Boundary-aware Substring Matching** - Handles ARNs, URLs, complex strings
- **Step 4: Fuzzy Matching** - Handles typos and naming variations
- **Step 5: Ghost Node Creation** - Creates external entity nodes for unmatched strings

## References

- **Algorithm**: Symbol Table Lookup
- **Implementation**: `implicit_dependency_resolver/exact_matching.py`
- **Dependencies**: Requires Step 1 (`taint_resolved_properties`) to be completed first
