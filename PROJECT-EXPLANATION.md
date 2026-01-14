# TerrARA Project Explanation

## Overview

TerrARA (TERRaform configurations-driven Architectural Risk Analysis) is an automated security threat modeling tool for Infrastructure as Code (IaC). It extracts Data Flow Diagrams (DFDs) from Terraform configuration files and automatically identifies security threats using the SPARTA threat modeling engine.

## Architecture Overview

The project follows a three-phase architecture:

1. **Phase 1: Preprocessing** - Converts Terraform configs to resource dependency graph
2. **Phase 2: Graph Analysis** - Transforms dependency graph to annotated DFD
3. **Phase 3: Threat Elicitation** - Analyzes DFD and generates security threats

---

## Phase 1: Preprocessing

### Purpose
Converts Terraform configuration files into a structured resource dependency graph stored in Memgraph (graph database).

### Key Files and Their Roles

#### `tfparser/tf2graph.py`
**Purpose**: Converts Terraform project to JSON graph representation

**Key Functions**:
- `GetJSON(folderPath, init, isTofu)`: Main entry point that orchestrates the conversion
  - Calls `InitTerraform()` to initialize Terraform project (removes `.terraform` directory and runs `terraform init`)
  - Calls `GenerateDotFile()` to run `terraform graph -type=plan` and generate DOT file
  - Calls `GenerateJSON()` to convert DOT to JSON using `terraform-graph-beautifier`
  - Returns path to JSON file containing graph structure

- `InitTerraform(folderPath, isTofu)`: 
  - Cleans up existing `.terraform` directory
  - Runs `terraform init` (either via Docker or directly if DOCKER_ENV=1)
  - Prepares project for graph generation

- `GenerateDotFile(folderPath, isTofu)`:
  - Executes `terraform graph -type=plan` command
  - Captures output and writes to temporary DOT file
  - Returns path to DOT file

- `GenerateJSON(dotPath)`:
  - Uses `terraform-graph-beautifier` tool to convert DOT format to Cytoscape JSON format
  - Removes orphan nodes (resources in state but not in config)
  - Returns path to JSON file

**Logic Flow**:
```
Terraform Project → terraform init → terraform graph → DOT file → terraform-graph-beautifier → JSON
```

#### `graph/graph.py`
**Purpose**: Loads JSON graph into Memgraph database and creates resource dependency graph

**Key Functions**:
- `LoadFromFolder(filePath, init=True)`:
  - Calls `GetJSON()` from `tfparser` module to get JSON representation
  - Gets encoded path ID using `GetPathID()` (converts absolute path to encoded format)
  - Parses JSON and creates nodes in Memgraph:
    - Each node has labels: `[encoded_path, resource_type]`
    - Properties: `parent_id`, `resource_type`, `resource_name`
  - Creates edges (relationships) between nodes based on dependencies
  - Returns encoded path ID for subsequent operations

**Node Structure in Memgraph**:
- Labels: `[pathID, "resource"]`
- Properties:
  - `parent`: Module path
  - `type`: Resource type (e.g., "aws_vpc")
  - `name`: Resource name (e.g., "km_vpc")

**Edge Structure**:
- Type: `REF` (directed relationship)
- Represents: Resource A depends on Resource B (A → B means A depends on B)

**Logic Flow**:
```
JSON Graph → Parse Nodes → Create Memgraph Nodes → Parse Edges → Create Memgraph Relationships → Resource Dependency Graph
```

#### `utils/n4j_helper.py`
**Purpose**: Provides low-level graph database operations for Memgraph/Neo4j

**Key Functions**:
- `Initialize()`: Establishes connection to Memgraph database (default: `bolt://localhost:7687`)
- `GetPathID(originPath)`: Converts absolute path to encoded format for multi-tenant database support
- `CreateNode(labels, values)`: Creates a node in Memgraph with specified labels and properties
- `AddConnection(fromId, targetId, pathId)`: Creates `REF` relationship between two nodes
- `CleanUp()`: Deletes all nodes and relationships (used for fresh start)

**Database Connection**:
- Uses Neo4j driver (compatible with Memgraph)
- URI: `bolt://localhost:7687` (configurable via `MEMGRAPH_URI` env var)
- Database: `memgraph`

---

## Phase 2: Graph Analysis

### Purpose
Transforms the resource dependency graph into an annotated Data Flow Diagram (DFD) by:
1. Tagging nodes as processes, data stores, or trust boundaries
2. Consolidating related resources into service nodes
3. Detecting public/exposed resources
4. Arranging components within trust boundaries
5. Identifying data flows between components

### Key Files and Their Roles

#### `main.py`
**Purpose**: Main orchestration file that coordinates all three phases

**Key Function**: `main(in_path, anno_path, rule_path, sem_rule, out_path, global_tb_name, reinit, graph_mode, verbose)`

**Phase 2 Logic Flow** (lines 39-207):

1. **Load Configuration Files** (lines 39-40):
   - `read_config(anno_path)`: Loads annotation rules (AWS service mappings)
   - `read_config(rule_path)`: Loads relationship rules (ownership, boundaries)

2. **Extract Compression and Public Resource Lists** (lines 44-51):
   - Identifies resources that need consolidation (`compress: true`)
   - Identifies resources that can be public (`can_public: true`)

3. **Initialize Graph Database** (lines 57-60):
   - `CleanUp()`: Clears previous data
   - `LoadFromFolder(in_path, init=reinit)`: Loads Terraform project into graph
   - Returns `pathID` for subsequent queries

4. **Tag Nodes** (lines 62-67):
   - Iterates through annotation rules (processes, data_stores, boundaries)
   - `TaggingNode()`: Matches resource types using regex patterns and tags nodes
   - Tags include: `tagged`, `processes`/`data_stores`/`boundaries`, `group`, `general_name`, `annotation`

5. **Cleanup Non-Tagged Nodes** (lines 69-70):
   - `RemoveNonTagged(pathID)`: Removes nodes that don't match any pattern
   - `Cleanup(pathID)`: Removes self-loops and optimizes graph

6. **Node Consolidation** (lines 72-74):
   - `CompressV2()`: Merges multiple resources of same type into single service node
   - Example: `aws_api_gateway_rest_api`, `aws_api_gateway_resource` → `APIGateway` service

7. **Link Tagged Nodes** (lines 76-77):
   - `LinkTagged(pathID)`: Creates direct connections between tagged nodes
   - Removes intermediate non-tagged nodes from paths

8. **Detect Public Boundaries** (lines 79-88):
   - `GetSemgrepJSON()`: Runs semgrep to detect public subnets
   - `TaggingPublic()`: Marks subnet resources as public
   - `RemovePublicBoundaries()`: Removes public subnet boundaries and rewires connections

9. **Build DFD Structure** (lines 91-187):
   - Creates `Diagram` object to hold DFD components
   - Processes ownership rules to arrange components within boundaries
   - `FindOwn()`: Finds relationships based on ownership rules (Backward/Forward)
   - Creates DFD components: `Process`, `DataStore`, `TrustBoundary`
   - `QueryOutermostBoundary()`: Finds top-level boundaries
   - `QueryAllConnectionResource()`: Finds data flows between components

10. **Export Results** (lines 198-207):
    - `graph_mode=True`: Exports DFD as PNG image using Graphviz
    - Otherwise: Exports to SPARTA format for threat analysis

#### `utils/n4j_helper.py` (Phase 2 Functions)

**Tagging Functions**:
- `TaggingNode(regexName, pathID, group, name, tag, annotation)`:
  - Matches nodes using regex pattern
  - Sets labels: `tagged`, `processes`/`data_stores`/`boundaries`
  - Sets properties: `group`, `general_name`, `annotation`

- `TaggingPublic(pathID, name)`:
  - Marks specific resource as public (exposed to external entities)
  - Adds `public` label to node

**Consolidation Functions**:
- `CompressV2(regexName, pathID)`:
  - Finds all nodes matching regex pattern
  - Keeps one representative node (highest degree)
  - Merges all connections from other nodes to representative
  - Deletes other matching nodes
  - Called multiple times for different resource types

**Query Functions**:
- `QueryTagged(pathID, group)`: Returns all tagged nodes of specific group
- `QueryOutermostBoundary(pathID)`: Finds boundaries with no parent boundaries
- `QueryAllConnectionResource(pathID)`: Returns direct connections between processes/data stores
- `FindOwn(firstNode, secondNode, method, pathID)`: Finds ownership relationships
  - `method="Backward"`: Second node → First node (e.g., Subnet → VPC)
  - `method="Forward"`: First node → Second node

**Cleanup Functions**:
- `RemoveNonTagged(pathID)`: Iteratively removes nodes not tagged as DFD components
  - Removes nodes with no tagged connections
  - Removes nodes that don't connect tagged nodes
- `RemovePublicBoundaries(pathID)`: Removes public subnet boundaries and rewires
- `LinkTagged(pathID)`: Creates direct connections between tagged nodes
- `Cleanup(pathID)`: Removes self-loops

#### `utils/yaml_importer.py`
**Purpose**: Loads YAML configuration files

**Key Function**:
- `read_config(path)`: Reads and parses YAML file, returns dictionary

#### `input/aws_annotation.yaml`
**Purpose**: Defines mapping rules from Terraform resources to DFD elements

**Structure**:
- `processes`: List of process groups (computational services)
  - Each group has: `group_name`, `annotation`, `members`
  - Each member has: `name`, `tf_name` (regex), `compress`, `can_public`
- `data_stores`: List of data store groups (storage services)
- `boundaries`: List of trust boundary groups (network boundaries)
- `external_entities`: List of external entities (users, external services)

**Example**:
```yaml
processes:
  - group_name: VirtualMachine
    annotation: VirtualMachine
    members:
      - name: EC2
        tf_name: aws_instance
        compress: true
```

**Usage**: Used to match Terraform resource types (`aws_instance`) to DFD components (`VirtualMachine` process)

#### `input/aws_rule.yaml`
**Purpose**: Defines relationship rules for arranging DFD components

**Structure**:
- `relations.own`: Ownership rules (which component belongs to which boundary)
  - `id`: Unique identifier
  - `first_node`: Target boundary group
  - `second_node`: Component group
  - `method`: Relationship direction (`Backward` or `Forward`)
- `publics`: Rules for detecting public resources using semgrep
  - `id`: Rule identifier
  - `variable`: Semgrep metavariable name

**Example**:
```yaml
relations:
  own:
    - id: subnet2vpc
      first_node: VirtualNetwork
      second_node: Subnet
      method: Backward  # Subnet depends on VPC
```

**Usage**: Determines how components are arranged within trust boundaries

#### `input/semgrep_rule.yaml`
**Purpose**: Defines semgrep patterns to detect public subnets

**Structure**:
- Rules use pattern matching to find subnets with:
  - `map_public_ip_on_launch = true`, OR
  - Route table with Internet Gateway route (`0.0.0.0/0`)

**Usage**: Identifies which subnets are public and should be removed from trust boundaries

#### `tfparser/tfgrep.py`
**Purpose**: Runs semgrep analysis on Terraform files

**Key Function**:
- `GetSemgrepJSON(folderPath, configPath)`:
  - Executes `semgrep --config=configPath --json folderPath`
  - Returns path to JSON file with pattern matching results
  - Used to detect public subnets

#### `dfdgraph/component.py`
**Purpose**: Defines DFD component classes (Process, DataStore, ExternalEntity)

**Key Classes**:
- `DFDNode`: Base class for all DFD components
  - Properties: `id`, `name`, `anno`, `dataflow` (list of DataFlow objects)
  - Methods: `DrawNode()`, `Get()`, `DrawEdge()`, `AddEdge()`
- `Process`: Represents computational components (circles in DFD)
- `DataStore`: Represents storage components (cylinders in DFD)
- `ExternalEntity`: Represents external actors (rectangles in DFD)

**Global Dictionary**: `COMPONENT_ID_NODE`: Maps component IDs to DFDNode instances

**Logic**:
- Each component maintains list of data flows
- `Get()` method creates SPARTA model element for threat analysis
- `AddEdge()` creates bidirectional data flow between components

#### `dfdgraph/trustboundary.py`
**Purpose**: Defines trust boundary class for DFD

**Key Class**:
- `TrustBoundary`: Represents security boundaries (dashed rectangles)
  - Properties: `name`, `nodes` (components inside), `innerBoundaries` (nested boundaries)
  - Methods: `AddNode()`, `AddInnerBound()`, `DrawBoundNode()`, `Get()`

**Global Dictionary**: `BOUNDARY_ID_NODE`: Maps boundary IDs to TrustBoundary instances

**Logic**:
- Boundaries can contain components and nested boundaries
- Used to group components with same security/trust level
- Example: VPC contains Subnets, Subnets contain EC2 instances

#### `dfdgraph/dataflow.py`
**Purpose**: Defines data flow class for DFD

**Key Class**:
- `DataFlow`: Represents data movement between components
  - Properties: `fromNode`, `toNode`, `label`
  - Creates bidirectional flows (assumes bidirectional communication)

**Global List**: `GLOBAL_DF_SP`: Stores all data flows for SPARTA export

**Logic**:
- Each data flow creates two SPARTA DataFlow objects (bidirectional)
- Used to represent communication paths in DFD

#### `dfdgraph/diagram.py`
**Purpose**: Main DFD diagram container class

**Key Class**:
- `Diagram`: Container for entire DFD
  - Properties: `publicNodes`, `boundaries`
  - Methods: `AddPublicNode()`, `AddBoundary()`, `ExportSparta()`, `DrawDiagram()`

**Key Methods**:
- `ExportSparta(path, external_entities)`:
  - Creates external entities and connects to public nodes
  - Exports all components, boundaries, and data flows to SPARTA format
  - Calls `ThreatAnalyze()` to generate threats
- `DrawDiagram(g, external_entities)`:
  - Uses Graphviz to draw DFD as PNG image
  - Separates node drawing and edge drawing (Graphviz bug workaround)

---

## Phase 3: Threat Elicitation

### Purpose
Analyzes the extracted DFD and automatically identifies security threats using SPARTA threat modeling engine.

### Key Files and Their Roles

#### `sparta_utils/sparta.py`
**Purpose**: Interface to SPARTA threat modeling engine

**Key Functions**:
- `Initialize(name)`: 
  - Loads SPARTA metamodel (`spartamodel.ecore`)
  - Loads threat catalog (`IACNewCatalog_v2.sparta`)
  - Creates DFD model instance
  - Returns tuple: `(ePkg, gModel, rset)`

- `SpartaComponent`: Static class for creating SPARTA model elements
  - `Process(name, anno)`: Creates SPARTA Process with annotation
  - `DataStore(name, anno)`: Creates SPARTA DataStore with annotation
  - `ExternalEntity(name, anno)`: Creates SPARTA ExternalEntity with annotation
  - `DataFlow(sender, recipient, name)`: Creates SPARTA DataFlow
  - `TrustBoundaryContainer(name)`: Creates SPARTA TrustBoundary

- `AddElement(e)`: Adds element to DFD model

- `Export(path)`: 
  - Saves DFD model to `.sparta` file format
  - Uses PyEcore to serialize model

- `ThreatAnalyze(csv_path, sparta_path)`:
  - Executes SPARTA CLI tool: `java -jar sparta-cli.jar -i sparta_path -pt catalog_path -oc csv_path`
  - Analyzes DFD against threat catalog
  - Generates CSV file with identified threats

**Logic Flow**:
```
DFD Components → SPARTA Model Elements → Export to .sparta file → SPARTA CLI Analysis → Threat CSV
```

#### `sparta_utils/IACNewCatalog_v2.sparta`
**Purpose**: Threat catalog containing 72 cloud-specific threat patterns

**Content**:
- Implements 66 patterns from Brazhuk's ACCTP (Academic Cloud Computing Threat Patterns)
- Adds 6 additional data store threats
- More fine-grained than generic STRIDE catalog
- Uses VIATRA model query patterns to match threats

**Threat Categories**:
- Broken Authentication
- Broken Access Control
- Data Breach
- Denial of Service
- Malware Injection
- And many more cloud-specific threats

**Usage**: SPARTA engine matches these patterns against DFD to identify threats

---

## Complete Execution Flow

### Step-by-Step Process

1. **User invokes main.py**:
   ```bash
   python main.py <terraform_project_path> [options]
   ```

2. **Phase 1 - Preprocessing**:
   - `main()` calls `LoadFromFolder()` → `GetJSON()` → `InitTerraform()` → `GenerateDotFile()` → `GenerateJSON()`
   - Terraform project initialized
   - Dependency graph generated as DOT file
   - DOT converted to JSON (removes orphan nodes)
   - JSON loaded into Memgraph database
   - Resource dependency graph created

3. **Phase 2 - Graph Analysis**:
   - Configuration files loaded (`aws_annotation.yaml`, `aws_rule.yaml`)
   - Nodes tagged based on annotation rules
   - Non-tagged nodes removed
   - Nodes consolidated (compression)
   - Public boundaries detected via semgrep
   - Public boundaries removed
   - Ownership rules applied to arrange components
   - DFD structure built (Processes, DataStores, TrustBoundaries)
   - Data flows identified
   - External entities connected to public nodes

4. **Phase 3 - Threat Elicitation**:
   - DFD components converted to SPARTA model elements
   - Model exported to `.sparta` file
   - SPARTA CLI analyzes model against threat catalog
   - Threats written to CSV file

### Output Files

- `output.sparta`: SPARTA model file (DFD in SPARTA format)
- `output.csv`: List of identified security threats
- `dfd.png`: Visual DFD diagram (if `graph_mode=True`)

---

## Key Design Decisions

### 1. Graph Database (Memgraph)
- **Why**: Efficient graph queries for complex relationships
- **Benefit**: Fast pattern matching and traversal
- **Trade-off**: Requires separate database service

### 2. Node Consolidation
- **Why**: Multiple Terraform resources represent single cloud service
- **Benefit**: Higher-level abstraction for threat modeling
- **Trade-off**: May lose some detail in data flows

### 3. Bidirectional Data Flows
- **Why**: Overapproximation for security analysis
- **Benefit**: Catches threats in both directions
- **Trade-off**: May generate false positives

### 4. Public Resource Detection
- **Why**: External entities need entry points
- **Benefit**: Identifies attack surfaces
- **Trade-off**: Overapproximation may mark non-public resources

### 5. Profile-Based Configuration
- **Why**: Extensibility for other cloud providers
- **Benefit**: Easy to add new resources and rules
- **Trade-off**: Requires manual rule creation

---

## File Organization Summary

```
TerrARA/
├── main.py                    # Main orchestration (all phases)
├── graph/                      # Phase 1: Graph loading
│   └── graph.py               # Load JSON into Memgraph
├── tfparser/                   # Phase 1: Terraform parsing
│   ├── tf2graph.py            # Convert Terraform to JSON graph
│   └── tfgrep.py              # Semgrep integration
├── utils/                      # Shared utilities
│   ├── n4j_helper.py           # Memgraph operations (Phase 1 & 2)
│   └── yaml_importer.py        # YAML config loader
├── dfdgraph/                   # Phase 2: DFD construction
│   ├── component.py           # Process, DataStore, ExternalEntity
│   ├── trustboundary.py        # TrustBoundary class
│   ├── dataflow.py             # DataFlow class
│   └── diagram.py              # Diagram container
├── sparta_utils/               # Phase 3: Threat analysis
│   ├── sparta.py               # SPARTA interface
│   └── IACNewCatalog_v2.sparta # Threat catalog
└── input/                      # Configuration files
    ├── aws_annotation.yaml     # Resource → DFD mapping
    ├── aws_rule.yaml           # Relationship rules
    └── semgrep_rule.yaml       # Public subnet detection
```

---

## Extension Points

### Adding New Cloud Provider

1. Create new annotation file (e.g., `azure_annotation.yaml`)
2. Create new rule file (e.g., `azure_rule.yaml`)
3. Define resource patterns and relationships
4. Pass files via command-line arguments

### Adding New Resource Types

1. Add entry to `aws_annotation.yaml`:
   ```yaml
   processes:
     - group_name: NewService
       annotation: CloudApplication
       members:
         - name: NewService
           tf_name: aws_new_service_\w*
           compress: true
           can_public: false
   ```

2. Add ownership rules to `aws_rule.yaml` if needed

### Adding New Threat Patterns

1. Edit `IACNewCatalog_v2.sparta` file
2. Define VIATRA query pattern
3. Specify threat description and mitigations

---

## Performance Considerations

- **Median execution time**: 42 seconds for 470 projects
- **Phase 1**: 77% of time (graph construction)
- **Phase 2**: 8% of time (graph analysis)
- **Phase 3**: 15% of time (threat elicitation)
- **Average DFD size**: 10 entities, 47 threats

---

## Limitations

1. **Implicit Communication**: Cannot detect hard-coded identifiers or DNS-based connections
2. **Node Consolidation**: May create dangling nodes or false positives
3. **Public Resource Detection**: Overapproximation may mark non-public resources
4. **Threat Prioritization**: No ranking system for threats
5. **Manual Rule Creation**: Requires domain expertise to create new rules

---

## Conclusion

TerrARA provides a systematic approach to automated threat modeling for Terraform IaC configurations. The three-phase architecture cleanly separates concerns: preprocessing handles Terraform parsing, graph analysis transforms to DFD, and threat elicitation identifies security risks. The profile-based configuration system enables extensibility while maintaining accuracy through careful pattern matching and graph analysis.

