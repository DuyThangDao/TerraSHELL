# Step 1: Taint Analysis & Variable Resolution

## Overview

Step 1 is the foundation of the 5-step pipeline for resolving implicit dependencies in Terraform. It performs **Constant Propagation** to resolve variable references (`var.xxx`, `local.xxx`) into their actual string values. Without this step, subsequent steps would not have the resolved data needed to detect implicit links.

**Role in Pipeline**: Preprocessing and data preparation

## Problem Statement

### Why Variable Resolution is Needed

Developers rarely hardcode values directly in resource definitions. Instead, they typically:

1. **Declare variables** in `variables.tf` with default values
2. **Use locals** in `locals.tf` to compute values
3. **Reference these variables** in resources using `var.xxx` or `local.xxx`

**Example Problem**:
```terraform
# variables.tf
variable "db_name" {
  default = "payment-db"
}

# main.tf
resource "aws_db_instance" "db" {
  db_name = var.db_name  # ← Variable reference, not literal string
}
```

When analyzing implicit dependencies, we need to know that `var.db_name` resolves to `"payment-db"` so that Step 2 can match it against resource names.

### What Step 1 Solves

- **Variable References**: Resolves `var.xxx` to actual values
- **Local References**: Resolves `local.xxx` to computed values
- **Nested References**: Handles chains like `var.a → var.b → "value"`
- **Default Value Propagation**: Traces through variable/local chains to find default values

## Algorithm: Constant Propagation

The algorithm uses **Constant Propagation** technique from compiler theory:

1. **Find Resources** that reference variables or locals via `REF` edges
2. **Trace Dependency Chain**: Follow `REF` edges from variable/local nodes
3. **Find Default Values**: Locate the final variable/local node with a default value
4. **Resolve References**: Replace variable references with actual string values
5. **Store Results**: Save resolved values on resource nodes

### Detailed Steps

#### Step 1: Find Resources with Variable References
```cypher
MATCH (r:resource)-[:REF]->(var_or_local)
WHERE var_or_local is Variable OR Local
```

#### Step 2: Extract Variable Name
Extract the variable/local name from the referenced node (e.g., `"db_name"` from `var.db_name`).

#### Step 3: Trace to Default Value
Follow `REF` edges through the variable/local chain until finding a node with:
- **Variable**: `default` property
- **Local**: `value` property

**Important**: Stop tracing when encountering a resource node (don't cross resource boundaries).

#### Step 4: Validate Value is "Clean"
Check that the resolved value doesn't contain unresolved references:
- No `${...}` syntax
- No `var.` references
- No `local.` references

#### Step 5: Store Resolved Values
Store two types of data on each resource node:

1. **`taint_resolved_values`**: JSON mapping variable names to resolved values
   ```json
   {
     "db_name": "payment-db",
     "env": "prod"
   }
   ```

2. **`taint_resolved_properties`**: JSON containing properties with resolved variable references
   ```json
   {
     "db_name": "payment-db",
     "security_groups": ["web-sg"]
   }
   ```

## Implementation Details

### Class: `TaintAnalyzer`

**Location**: `implicit_dependency_resolver/taint_analysis.py`

**Main Method**: `propagate_constants()`

### Key Helper Methods

1. **`_has_variable_reference(text)`**: Detects if string contains `var.xxx` or `${var.xxx}`
2. **`_has_resolved_variable_reference(text, var_values)`**: Checks if variable is resolvable
3. **`_replace_variables_in_string(text, var_values)`**: Replaces variable references with values
4. **`_resolve_properties(properties, var_values)`**: Resolves variables in nested property structures
5. **`_resolve_nested_value_if_has_var(value, var_values)`**: Recursively resolves nested dicts/lists

### Cypher Query Structure

The main query performs:
1. Match resources with direct variable/local references
2. Extract variable names
3. Trace paths through variable/local nodes (max 10 hops)
4. Filter paths to exclude resource nodes
5. Find final variable/local with default value
6. Validate value is clean
7. Return resource_id, var_name, resolved_value

## Data Structures

### Input
- Graph nodes with `REF` relationships between resources and variables/locals
- Variable nodes with `default` property
- Local nodes with `value` property

### Output
Two properties stored on resource nodes:

#### `taint_resolved_values` (JSON string)
Maps variable names to their resolved values:
```json
{
  "db_name": "payment-db",
  "app_name": "my-app",
  "env": "production"
}
```

#### `taint_resolved_properties` (JSON string)
Contains properties where variable references were resolved:
```json
{
  "db_name": "payment-db",
  "security_groups": ["web-sg", "db-sg"],
  "subnet_id": "private-subnet-1"
}
```

## Usage

### Basic Usage
```python
from implicit_dependency_resolver.taint_analysis import TaintAnalyzer
from utils.n4j_helper import GetPathID

project_path = "/path/to/terraform/project"
path_id = GetPathID(project_path)

analyzer = TaintAnalyzer(path_id)
analyzer.run()  # Executes propagate_constants() and logs results
```

### Integration in Pipeline
Step 1 is typically called after graph enrichment:
```python
# In phase1_enrich_graph.py
from implicit_dependency_resolver.taint_analysis import TaintAnalyzer

analyzer = TaintAnalyzer(path_id)
taint_count = analyzer.propagate_constants()
logger.info(f"Taint Analysis completed: {taint_count} resources resolved")
```

## Examples

### Example 1: Simple Variable Resolution

**Before Step 1**:
```terraform
# variables.tf
variable "sg_name" {
  default = "web-sg"
}

# main.tf
resource "aws_security_group" "sg" {
  name = var.sg_name
}
```

**After Step 1**:
- Resource node has `taint_resolved_properties`:
  ```json
  {
    "name": "web-sg"
  }
  ```

### Example 2: Variable Chain Resolution

**Before Step 1**:
```terraform
# variables.tf
variable "env" {
  default = "prod"
}

variable "sg_name" {
  default = "${var.env}-sg"  # References var.env
}

# main.tf
resource "aws_security_group" "sg" {
  name = var.sg_name
}
```

**After Step 1**:
- Step 1 traces: `var.sg_name → var.env → "prod"`
- Resource node has `taint_resolved_properties`:
  ```json
  {
    "name": "prod-sg"
  }
  ```

### Example 3: Local Resolution

**Before Step 1**:
```terraform
# locals.tf
locals {
  db_name = "payment-db"
}

# main.tf
resource "aws_db_instance" "db" {
  db_name = local.db_name
}
```

**After Step 1**:
- Resource node has `taint_resolved_properties`:
  ```json
  {
    "db_name": "payment-db"
  }
  ```

## Limitations

### What Step 1 Does NOT Handle

1. **Unresolved Variables**: Variables without default values cannot be resolved
   ```terraform
   variable "api_key" {
     # No default - cannot resolve
   }
   ```

2. **Complex Interpolation**: String interpolation with multiple variables
   ```terraform
   name = "${var.env}-${var.app}-sg"  # Partially resolved if only one var has default
   ```

3. **Dynamic Values**: Values computed at runtime (not in Terraform config)
   ```terraform
   name = random_string.id.result  # Cannot resolve without executing Terraform
   ```

4. **Module Outputs**: References to module outputs (future enhancement)

5. **Data Source References**: References to `data` resources (future enhancement)

### Edge Cases

- **Circular References**: Variables referencing each other (handled by max hop limit)
- **Missing Defaults**: Variables in chain without defaults (skipped)
- **Non-String Values**: Non-string default values (converted to string)

## Next Steps

After Step 1 completes, proceed to:
- **Step 2: Exact Matching** - Uses `taint_resolved_properties` to match strings against resource names

## References

- **Algorithm**: Constant Propagation (Compiler Theory)
- **Implementation**: `implicit_dependency_resolver/taint_analysis.py`
- **Integration**: `phase1_enrich_graph.py`
