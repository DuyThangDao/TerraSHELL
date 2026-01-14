# Phase 1: Preprocessing - Manual Execution Guide

## Overview

Phase 1 converts Terraform configuration files into a structured resource dependency graph stored in Memgraph (graph database). This guide walks you through manually executing Phase 1 step-by-step using the `demo_tf_project` as an example.

## Quick Start

**Automated execution** (recommended for first-time users):
```bash
cd /home/thangdd/repos/TerrARA
./phase1_quick_start.sh
```

**Manual execution** (for learning/debugging):
1. Follow steps 1-4 in this guide
2. Use provided Python scripts: `phase1_load_graph.py` and `phase1_query_graph.py`

**Expected time**: 2-5 minutes for demo_tf_project

## Prerequisites

### 1. Required Services

**Memgraph Database**:
```bash
# Start Memgraph using Docker Compose
cd /home/thangdd/repos/TerrARA
docker compose -f memgraph-compose.yaml up -d
```

Verify Memgraph is running:
- **Memgraph**: `bolt://localhost:7687`
- **Memgraph Lab** (Web UI): `http://localhost:3000`

### 2. Required Tools

- **Terraform**: Version 1.8.0+ (or Docker with `hashicorp/terraform:1.8.0-rc2`)
- **terraform-graph-beautifier**: Available via Docker (`ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux`)
- **Python 3.x** with dependencies installed
- **Neo4j Python Driver**: For Memgraph connectivity

### 3. Project Structure

```
TerrARA/
├── demo_tf_project/          # Your Terraform project
│   ├── main.tf              # EC2, Security Group, S3 resources
│   ├── variables.tf
│   ├── provider.tf
│   └── output.tf
├── tfparser/                 # Phase 1 modules
│   ├── tf2graph.py          # Terraform → JSON conversion
│   └── tfgrep.py
├── graph/                    # Phase 1 modules
│   └── graph.py              # JSON → Memgraph loading
├── utils/
│   ├── n4j_helper.py         # Memgraph operations
│   └── random_tmp.py          # Temporary file management
└── tmp/                      # Temporary files (created automatically)
```

---

## Phase 1 Execution Steps

### Step 1: Initialize Terraform Project

**Purpose**: Prepare Terraform project for graph generation by initializing providers and modules.

**File**: `tfparser/tf2graph.py` → `InitTerraform()`

**Manual Execution**:

```bash
cd /home/thangdd/repos/TerrARA/demo_tf_project

# Clean up previous initialization (if exists)
rm -rf .terraform .terraform.lock.hcl

# Initialize Terraform
terraform init
```

**Expected Output**:
```
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions matching ~> 5.0...
- Installing hashicorp/aws 5.x.x...
Terraform has been successfully initialized!
```

**What Happens**:
- Downloads AWS provider plugin
- Prepares backend for state management
- Creates `.terraform/` directory with provider binaries

**Verification**:
```bash
ls -la .terraform/
# Should see: providers/ directory
```

---

### Step 2: Generate Dependency Graph (DOT Format)

**Purpose**: Generate Terraform's internal dependency graph in DOT format.

**File**: `tfparser/tf2graph.py` → `GenerateDotFile()`

**Manual Execution**:

```bash
cd /home/thangdd/repos/TerrARA/demo_tf_project

# Generate DOT graph
terraform graph -type=plan > /tmp/terraform_graph.dot

# View the DOT file
cat /tmp/terraform_graph.dot
```

**Expected Output** (DOT format):
```dot
digraph {
    compound = "true"
    newrank = "true"
    subgraph "root" {
        "[root] aws_instance.app_server" -> "[root] aws_security_group.web_sg"
        "[root] aws_instance.app_server" -> "[root] data.aws_ami.amazon_linux"
        "[root] aws_security_group.web_sg" -> "[root] provider[\"registry.terraform.io/hashicorp/aws\"]"
        "[root] aws_s3_bucket.data_storage" -> "[root] provider[\"registry.terraform.io/hashicorp/aws\"]"
        "[root] data.aws_ami.amazon_linux" -> "[root] provider[\"registry.terraform.io/hashicorp/aws\"]"
        ...
    }
}
```

**What Happens**:
- Terraform analyzes resource dependencies
- Creates directed graph showing creation order
- Edge `A → B` means: "Resource A depends on Resource B" (B must be created first)

**Understanding the Graph**:
- **Nodes**: Resources, data sources, providers, variables
- **Edges**: Dependencies (creation order)
- **Example**: `aws_instance.app_server` depends on `aws_security_group.web_sg` and `data.aws_ami.amazon_linux`

**For demo_tf_project, you should see**:
- `aws_security_group.web_sg` (Security Group)
- `aws_instance.app_server` (EC2 Instance) → depends on Security Group and AMI data
- `aws_s3_bucket.data_storage` (S3 Bucket)
- `data.aws_ami.amazon_linux` (AMI Data Source)

**Visualization** (optional):
```bash
# Convert DOT to PNG (requires graphviz)
dot -Tpng /tmp/terraform_graph.dot -o /tmp/terraform_graph.png
```

---

### Step 3: Convert DOT to JSON (Remove Orphan Nodes)

**Purpose**: Convert DOT format to structured JSON and remove orphan nodes (resources in state but not in config).

**File**: `tfparser/tf2graph.py` → `GenerateJSON()`

**Manual Execution**:

```bash
# Using Docker (recommended)
docker run --rm \
  --platform linux/amd64 \
  -v /tmp/terraform_graph.dot:/app/d.dot \
  ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux \
  -input /app/d.dot \
  --output-type=cyto-json > /tmp/terraform_graph.json

# Or using local installation (if available)
terraform-graph-beautifier \
  -input /tmp/terraform_graph.dot \
  --output-type=cyto-json > /tmp/terraform_graph.json
```

**Expected Output** (JSON structure):
```json
{
  "nodes": [
    {
      "data": {
        "id": "aws_security_group.web_sg",
        "parent": "",
        "label": "aws_security_group.web_sg",
        "type": "resource"
      },
      "classes": ["resource"]
    },
    {
      "data": {
        "id": "aws_instance.app_server",
        "parent": "",
        "label": "aws_instance.app_server",
        "type": "resource"
      },
      "classes": ["resource"]
    },
    {
      "data": {
        "id": "aws_s3_bucket.data_storage",
        "parent": "",
        "label": "aws_s3_bucket.data_storage",
        "type": "resource"
      },
      "classes": ["resource"]
    },
    {
      "data": {
        "id": "data.aws_ami.amazon_linux",
        "parent": "",
        "label": "data.aws_ami.amazon_linux",
        "type": "data"
      },
      "classes": ["data"]
    }
  ],
  "edges": [
    {
      "data": {
        "id": "aws_instance.app_server-aws_security_group.web_sg",
        "source": "aws_instance.app_server",
        "target": "aws_security_group.web_sg",
        "sourceType": "resource",
        "targetType": "resource"
      },
      "classes": ["resource-resource"]
    },
    {
      "data": {
        "id": "aws_instance.app_server-data.aws_ami.amazon_linux",
        "source": "aws_instance.app_server",
        "target": "data.aws_ami.amazon_linux",
        "sourceType": "resource",
        "targetType": "data"
      },
      "classes": ["resource-data"]
    }
  ]
}
```

**What Happens**:
- Converts DOT to Cytoscape JSON format
- **Removes orphan nodes**: Resources in state file but not in current config
- Structures nodes and edges for programmatic processing

**Key Fields**:
- **nodes[].data.id**: Full resource identifier
- **nodes[].data.type**: Node type (`resource`, `data`, `variable`, `module`, etc.)
- **nodes[].data.parent**: Module path (empty for root)
- **edges[].data.source/target**: Dependency relationship

**Verification**:
```bash
# Count nodes
cat /tmp/terraform_graph.json | jq '.nodes | length'

# Count edges
cat /tmp/terraform_graph.json | jq '.edges | length'

# List all resource types
cat /tmp/terraform_graph.json | jq '.nodes[] | select(.data.type == "resource") | .data.label'
```

**For demo_tf_project, expect**:
- **4 nodes**: 3 resources (`aws_security_group`, `aws_instance`, `aws_s3_bucket`) + 1 data source (`data.aws_ami`)
- **2 edges**: EC2 → Security Group, EC2 → AMI data

---

### Step 4: Load JSON into Memgraph Database

**Purpose**: Import the JSON graph into Memgraph for efficient graph queries and analysis.

**File**: `graph/graph.py` → `LoadFromFolder()`

**Manual Execution** (Python script):

Create a script `phase1_load_graph.py`:

```python
#!/usr/bin/env python3
import json
import sys
import os

# Add project root to path
sys.path.insert(0, '/home/thangdd/repos/TerrARA')

from utils.n4j_helper import Initialize, CreateNode, AddConnection, GetPathID, CleanUp

# Initialize connection
INSTANCE = Initialize()

# Clean up previous data (optional)
CleanUp()

# Load JSON file
json_path = '/tmp/terraform_graph.json'
data = json.load(open(json_path, 'r'))

# Get encoded path ID
project_path = '/home/thangdd/repos/TerrARA/demo_tf_project'
pathID = GetPathID(project_path)
print(f"Path ID: {pathID}")

# Create node mapping
nodeInvMap = {}

# Create all nodes
print("\n=== Creating Nodes ===")
for node in data["nodes"]:
    source = node["data"]
    
    # Extract resource type and name
    label_parts = source["label"].split(".")
    resource_type = label_parts[0]  # e.g., "aws_security_group"
    resource_name = ".".join(label_parts[1:]) if len(label_parts) > 1 else ""
    
    node_id = CreateNode(
        [pathID, source["type"]],  # Labels: [pathID, "resource" or "data"]
        {
            "parent_id": source.get("parent", ""),
            "resource_type": resource_type,
            "resource_name": resource_name
        }
    )
    
    nodeInvMap[source["id"]] = node_id
    print(f"Created node: {source['label']} → ID: {node_id}")

# Create all edges
print("\n=== Creating Edges ===")
if data.get("edges"):
    for edge in data["edges"]:
        source_id = nodeInvMap.get(edge["data"]["source"])
        target_id = nodeInvMap.get(edge["data"]["target"])
        
        if source_id and target_id:
            AddConnection(source_id, target_id, pathID)
            print(f"Created edge: {edge['data']['source']} → {edge['data']['target']}")

print(f"\n=== Phase 1 Complete ===")
print(f"Total nodes created: {len(nodeInvMap)}")
print(f"Total edges created: {len(data.get('edges', []))}")
print(f"\nPath ID for queries: {pathID}")
```

**Execute**:
```bash
cd /home/thangdd/repos/TerrARA
python3 phase1_load_graph.py
```

**Expected Output**:
```
Path ID: home.thangdd.repos.TerrARA.demo_tf_project

=== Creating Nodes ===
Created node: aws_security_group.web_sg → ID: 0
Created node: aws_instance.app_server → ID: 1
Created node: aws_s3_bucket.data_storage → ID: 2
Created node: data.aws_ami.amazon_linux → ID: 3

=== Creating Edges ===
Created edge: aws_instance.app_server → aws_security_group.web_sg
Created edge: aws_instance.app_server → data.aws_ami.amazon_linux

=== Phase 1 Complete ===
Total nodes created: 4
Total edges created: 2

Path ID for queries: home.thangdd.repos.TerrARA.demo_tf_project
```

**What Happens**:
- Connects to Memgraph database
- Creates nodes with labels `[pathID, "resource"]` or `[pathID, "data"]`
- Sets properties: `parent`, `type`, `name`
- Creates `REF` relationships between nodes
- Returns `pathID` for subsequent queries

**Node Structure in Memgraph**:
```
Node ID: 0
Labels: [home.thangdd.repos.TerrARA.demo_tf_project, resource]
Properties:
  - parent: ""
  - type: "aws_security_group"
  - name: "web_sg"
```

**Edge Structure**:
```
Relationship Type: REF
From: Node ID 1 (aws_instance.app_server)
To: Node ID 0 (aws_security_group.web_sg)
```

---

## Reviewing Phase 1 Output

### Method 1: Memgraph Lab (Web UI) - Recommended

**Access**: Open browser to `http://localhost:3000`

**Steps**:
1. Click "Connect" (should auto-connect to `bolt://localhost:7687`)
2. In the query editor, run:

```cypher
// View all nodes
MATCH (n)
RETURN n
LIMIT 100
```

3. Click "Run" to visualize the graph

**Query Examples**:

```cypher
// View all resource nodes
MATCH (n:resource)
RETURN n.type, n.name, ID(n) as node_id
ORDER BY n.type

// View all relationships
MATCH (a)-[r:REF]->(b)
RETURN a.type, a.name, b.type, b.name, ID(a) as from_id, ID(b) as to_id

// View dependency chain for EC2 instance
MATCH path = (n {name: "app_server"})-[*]->(m)
RETURN path
LIMIT 50

// Count nodes by type
MATCH (n)
RETURN labels(n)[1] as node_type, count(*) as count
ORDER BY count DESC
```

### Method 2: Python Script Queries

Create `phase1_query_graph.py`:

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/thangdd/repos/TerrARA')

from utils.n4j_helper import Initialize, GetPathID

INSTANCE = Initialize()
pathID = GetPathID('/home/thangdd/repos/TerrARA/demo_tf_project')

# Query 1: List all nodes
print("=== All Nodes ===")
records, _, _ = INSTANCE.execute_query(
    f"MATCH (n:{pathID}) RETURN ID(n) as id, n.type as type, n.name as name, labels(n) as labels",
    database_="memgraph"
)
for r in records:
    print(f"ID: {r['id']}, Type: {r['type']}, Name: {r['name']}, Labels: {r['labels']}")

# Query 2: List all edges
print("\n=== All Edges ===")
records, _, _ = INSTANCE.execute_query(
    f"MATCH (a:{pathID})-[r:REF]->(b:{pathID}) RETURN ID(a) as from_id, a.type as from_type, a.name as from_name, ID(b) as to_id, b.type as to_type, b.name as to_name",
    database_="memgraph"
)
for r in records:
    print(f"{r['from_type']}.{r['from_name']} → {r['to_type']}.{r['to_name']}")

# Query 3: Count statistics
print("\n=== Statistics ===")
records, _, _ = INSTANCE.execute_query(
    f"MATCH (n:{pathID}) RETURN count(n) as node_count",
    database_="memgraph"
)
print(f"Total nodes: {records[0]['node_count']}")

records, _, _ = INSTANCE.execute_query(
    f"MATCH ()-[r:REF]->() RETURN count(r) as edge_count",
    database_="memgraph"
)
print(f"Total edges: {records[0]['edge_count']}")
```

**Execute**:
```bash
python3 phase1_query_graph.py
```

### Method 3: Cypher Shell (Command Line)

```bash
# Connect to Memgraph
docker exec -it memgraph-mage cypher-shell

# Run queries
MATCH (n) RETURN n LIMIT 10;
MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 10;
```

---

## Expected Output for demo_tf_project

### Nodes Created:
1. **aws_security_group.web_sg**
   - Type: `resource`
   - Name: `web_sg`
   - Properties: Allows SSH (22) and HTTP (80) from 0.0.0.0/0

2. **aws_instance.app_server**
   - Type: `resource`
   - Name: `app_server`
   - Dependencies: Security Group, AMI data

3. **aws_s3_bucket.data_storage**
   - Type: `resource`
   - Name: `data_storage`
   - Independent resource (no dependencies)

4. **data.aws_ami.amazon_linux**
   - Type: `data`
   - Name: `amazon_linux`
   - Data source for AMI lookup

### Edges Created:
1. `aws_instance.app_server` → `aws_security_group.web_sg`
   - EC2 depends on Security Group

2. `aws_instance.app_server` → `data.aws_ami.amazon_linux`
   - EC2 depends on AMI data

### Graph Visualization:
```
[data.aws_ami.amazon_linux]
         ↑
         |
[aws_instance.app_server] → [aws_security_group.web_sg]

[aws_s3_bucket.data_storage]  (isolated)
```

---

## Troubleshooting

### Issue 1: Memgraph Connection Failed

**Error**: `Cannot connect to server at bolt://localhost:7687`

**Solution**:
```bash
# Check if Memgraph is running
docker ps | grep memgraph

# Start Memgraph
docker compose -f memgraph-compose.yaml up -d

# Check logs
docker logs memgraph-mage
```

### Issue 2: Terraform Init Fails

**Error**: Provider download failed or authentication issues

**Solution**:
```bash
# Check AWS credentials (if using AWS provider)
aws configure list

# Try with Docker (isolated environment)
docker run --rm -v $(pwd):/app hashicorp/terraform:1.8.0-rc2 -chdir=/app init
```

### Issue 3: JSON File Empty or Invalid

**Error**: `terraform-graph-beautifier` produces empty output

**Solution**:
```bash
# Verify DOT file is valid
cat /tmp/terraform_graph.dot | head -20

# Check if terraform graph worked
terraform graph -type=plan | head -20

# Try alternative: use terraform graph directly
terraform graph -type=plan -draw-cycles | dot -Tjson > /tmp/terraform_graph.json
```

### Issue 4: Node Creation Fails

**Error**: Duplicate nodes or invalid labels

**Solution**:
```python
# Clean up database first
from utils.n4j_helper import CleanUp
CleanUp()

# Then reload
```

### Issue 5: Path ID Encoding Issues

**Error**: Path ID contains invalid characters

**Solution**:
```python
# Check path encoding
from utils.n4j_helper import GetPathID
pathID = GetPathID('/home/thangdd/repos/TerrARA/demo_tf_project')
print(f"Encoded path: {pathID}")
# Should output: home.thangdd.repos.TerrARA.demo_tf_project
```

---

## Verification Checklist

After completing Phase 1, verify:

- [ ] Terraform project initialized successfully (`.terraform/` exists)
- [ ] DOT file generated (`terraform graph` works)
- [ ] JSON file created and valid (can parse with `jq`)
- [ ] Memgraph database running (`docker ps` shows memgraph-mage)
- [ ] Nodes created in Memgraph (query returns nodes)
- [ ] Edges created correctly (query returns relationships)
- [ ] Path ID matches project location
- [ ] All resources from `demo_tf_project` are present in graph

---

## Next Steps: Phase 2

After Phase 1 completes successfully, you have:
- ✅ Resource dependency graph in Memgraph
- ✅ All Terraform resources as nodes
- ✅ Dependency relationships as edges

**Phase 2** will:
- Tag nodes as Processes, Data Stores, or Trust Boundaries
- Consolidate related resources into services
- Detect public/exposed resources
- Arrange components within trust boundaries
- Build the final DFD structure

---

## Quick Reference: Phase 1 Functions

| Function | File | Purpose |
|----------|------|---------|
| `InitTerraform()` | `tfparser/tf2graph.py` | Initialize Terraform project |
| `GenerateDotFile()` | `tfparser/tf2graph.py` | Generate DOT dependency graph |
| `GenerateJSON()` | `tfparser/tf2graph.py` | Convert DOT to JSON |
| `GetJSON()` | `tfparser/tf2graph.py` | Orchestrate all conversion steps |
| `LoadFromFolder()` | `graph/graph.py` | Load JSON into Memgraph |
| `CreateNode()` | `utils/n4j_helper.py` | Create node in Memgraph |
| `AddConnection()` | `utils/n4j_helper.py` | Create edge in Memgraph |
| `GetPathID()` | `utils/n4j_helper.py` | Encode project path |

---

## Summary

Phase 1 transforms Terraform configuration files into a queryable graph database:

```
Terraform Files
    ↓ [terraform init]
Initialized Project
    ↓ [terraform graph]
DOT File (dependency graph)
    ↓ [terraform-graph-beautifier]
JSON File (structured graph)
    ↓ [LoadFromFolder]
Memgraph Database (queryable graph)
```

**Output**: Resource dependency graph ready for Phase 2 analysis.

