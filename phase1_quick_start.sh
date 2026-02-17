#!/bin/bash
# Phase 1 Quick Start Script for demo_tf_project
# This script automates the manual steps described in PHASE1-MANUAL-GUIDE.md

set -e  # Exit on error

PROJECT_DIR="/home/thangdd/repos/TerrARA/terraform-project/implicit_resolver_step_1"
SCRIPT_DIR="/home/thangdd/repos/TerrARA"
TMP_DIR="/tmp"

echo "=========================================="
echo "Phase 1: Preprocessing - Quick Start"
echo "=========================================="
echo ""

# Step 1: Check prerequisites
echo "[1/9] Checking prerequisites..."
if ! command -v terraform &> /dev/null && ! docker ps &> /dev/null; then
    echo "Error: Terraform or Docker required"
    exit 1
fi

if ! docker ps | grep -q memgraph-mage; then
    echo "Warning: Memgraph not running. Starting Memgraph..."
    cd "$SCRIPT_DIR"
    docker compose -f memgraph-compose.yaml up -d
    sleep 5
fi
echo "✓ Prerequisites OK"
echo ""

# Step 2: Initialize Terraform
echo "[2/9] Initializing Terraform project..."
cd "$PROJECT_DIR"
if [ -d ".terraform" ]; then
    echo "  Cleaning up previous initialization..."
    # Fix permissions in case files were created by Docker (owned by root)
    chmod -R u+w .terraform 2>/dev/null || true
    # Try to remove, use sudo if permission denied (files may be owned by root from Docker)
    rm -rf .terraform .terraform.lock.hcl 2>/dev/null || {
        echo "  Some files may be owned by root, trying with sudo..."
        sudo rm -rf .terraform .terraform.lock.hcl
    }
fi

if command -v terraform &> /dev/null; then
    terraform init
else
    echo "  Using Docker for Terraform..."
    docker run --rm \
        --platform linux/amd64 \
        -v "$(pwd):/app" \
        hashicorp/terraform:1.8.0-rc2 \
        -chdir=/app init
fi
echo "✓ Terraform initialized"
echo ""

# Step 3: Generate DOT file
echo "[3/9] Generating dependency graph (DOT format)..."
DOT_FILE="$TMP_DIR/terraform_graph_$(date +%s).dot"

if command -v terraform &> /dev/null; then
    terraform graph -type=plan > "$DOT_FILE"
else
    docker run --rm \
        --platform linux/amd64 \
        -v "$(pwd):/app" \
        hashicorp/terraform:1.8.0-rc2 \
        -chdir=/app graph -type=plan > "$DOT_FILE"
fi

if [ ! -s "$DOT_FILE" ]; then
    echo "Error: DOT file is empty"
    exit 1
fi
echo "✓ DOT file generated: $DOT_FILE"
echo "  File size: $(wc -l < "$DOT_FILE") lines"
echo ""

# Step 4: Convert DOT to JSON
echo "[4/9] Converting DOT to JSON..."
JSON_FILE="$TMP_DIR/terraform_graph_$(date +%s).json"

docker run --rm \
    --platform linux/amd64 \
    -v "$DOT_FILE:/app/d.dot" \
    ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux \
    -input /app/d.dot \
    --output-type=cyto-json > "$JSON_FILE"

if [ ! -s "$JSON_FILE" ]; then
    echo "Error: JSON file is empty"
    exit 1
fi

NODE_COUNT=$(python3 -c "import json; print(len(json.load(open('$JSON_FILE'))['nodes']))" 2>/dev/null || echo "?")
EDGE_COUNT=$(python3 -c "import json; print(len(json.load(open('$JSON_FILE'))['edges']))" 2>/dev/null || echo "?")
echo "✓ JSON file generated: $JSON_FILE"
echo "  Nodes: $NODE_COUNT, Edges: $EDGE_COUNT"
echo ""

# Step 5: Load into Memgraph
echo "[5/9] Loading graph into Memgraph..."
cd "$SCRIPT_DIR"
python3 phase1_load_graph.py "$JSON_FILE" "$PROJECT_DIR"
echo ""

# Step 5.5: Enrich Graph with HCL Properties (includes Taint Analysis preprocessing)
echo "[5.5/9] Enriching graph with properties from HCL..."
cd "$SCRIPT_DIR"
python3 implicit_dependency_resolver/taint_analysis.py "$PROJECT_DIR"
echo ""

# Step 6: Run Exact Matching to create implicit dependency links
echo "[6/9] Running Exact Matching to create implicit dependency links..."
python3 implicit_dependency_resolver/exact_matching.py "$PROJECT_DIR"
echo "✓ Exact Matching complete"
echo ""

# Step 7: Run Boundary-aware Substring Matching to create implicit dependency links
echo "[7/9] Running Boundary-aware Substring Matching to create implicit dependency links..."
python3 implicit_dependency_resolver/boundary_aware_matching.py "$PROJECT_DIR"
echo "✓ Boundary-aware Matching complete"
echo ""

# Step 8: Run Fuzzy & Heuristic Matching to create implicit dependency links
echo "[8/9] Running Fuzzy & Heuristic Matching to create implicit dependency links..."
python3 implicit_dependency_resolver/fuzzy_matching.py "$PROJECT_DIR"
echo "✓ Fuzzy & Heuristic Matching complete"
echo ""

# # Step 9: Run Ghost Node Creation to create external entity nodes
# echo "[9/9] Running Ghost Node Creation to create external entity nodes..."
# python3 phase1_ghost_node_creation.py "$PROJECT_DIR"
# echo "✓ Ghost Node Creation complete"
# echo ""

echo "=========================================="
echo "Phase 1 Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Review graph: python3 phase1_query_graph.py $PROJECT_DIR"
echo "  2. Visualize: Open http://localhost:3000 (Memgraph Lab)"
echo "  3. Continue to Phase 2: python3 main.py $PROJECT_DIR"
echo ""
echo "Files created:"
echo "  - DOT: $DOT_FILE"
echo "  - JSON: $JSON_FILE"
echo ""

