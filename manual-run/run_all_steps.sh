#!/bin/bash
# Script để chạy tất cả các steps tuần tự

set -e  # Exit on error

TERRAFORM_PATH=$1
if [ -z "$TERRAFORM_PATH" ]; then
    echo "Usage: $0 <terraform_project_path>"
    echo "Example: $0 ./terraform-project/AWSGoat"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Running all steps sequentially${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1
echo -e "${YELLOW}[1/18] Initializing...${NC}"
python3 manual-run/step_01_initialize.py "$TERRAFORM_PATH" || { echo -e "${RED}Step 1 failed!${NC}"; exit 1; }

# Step 2
echo -e "${YELLOW}[2/18] Cleaning database...${NC}"
python3 manual-run/step_02_cleanup_db.py || { echo -e "${RED}Step 2 failed!${NC}"; exit 1; }

# Step 3
echo -e "${YELLOW}[3/19] Loading graph...${NC}"
python3 manual-run/step_03_load_graph.py || { echo -e "${RED}Step 3 failed!${NC}"; exit 1; }

# Step 4a: Enrich Graph (Properties Only) - Phase 1.5a
# Run BEFORE Tag/RemoveNonTagged to ensure properties are enriched before nodes are deleted
echo -e "${YELLOW}[4/19] Enriching graph properties...${NC}"
python3 manual-run/step_04a_enrich_only.py || { echo -e "${RED}Step 4a failed!${NC}"; exit 1; }

# Step 5
echo -e "${YELLOW}[5/19] Tagging nodes...${NC}"
python3 manual-run/step_05_tag_nodes.py || { echo -e "${RED}Step 5 failed!${NC}"; exit 1; }

# Step 6
echo -e "${YELLOW}[6/19] Removing non-tagged nodes...${NC}"
python3 manual-run/step_06_remove_nontagged.py || { echo -e "${RED}Step 6 failed!${NC}"; exit 1; }

# Step 7
echo -e "${YELLOW}[7/19] Cleaning up...${NC}"
python3 manual-run/step_07_cleanup.py || { echo -e "${RED}Step 7 failed!${NC}"; exit 1; }

# Step 8
echo -e "${YELLOW}[8/19] Compressing nodes...${NC}"
python3 manual-run/step_08_compress.py || { echo -e "${RED}Step 8 failed!${NC}"; exit 1; }

# Step 4b: Implicit Matching (Edges Only) - Phase 1.5b
# Run AFTER Compress to ensure edges are created at compressed level
echo -e "${YELLOW}[9/19] Running implicit matching...${NC}"
python3 manual-run/step_04b_matching_only.py || { echo -e "${RED}Step 4b failed!${NC}"; exit 1; }

# Step 9
echo -e "${YELLOW}[10/19] Linking tagged nodes...${NC}"
python3 manual-run/step_09_link_tagged.py || { echo -e "${RED}Step 9 failed!${NC}"; exit 1; }

# Step 10
echo -e "${YELLOW}[11/19] Removing non-tagged nodes again...${NC}"
python3 manual-run/step_10_remove_nontagged_again.py || { echo -e "${RED}Step 10 failed!${NC}"; exit 1; }

# Step 11
echo -e "${YELLOW}[12/19] Running Semgrep...${NC}"
python3 manual-run/step_11_semgrep_public.py || { echo -e "${RED}Step 11 failed!${NC}"; exit 1; }

# Step 12
echo -e "${YELLOW}[13/19] Removing public boundaries...${NC}"
python3 manual-run/step_12_remove_public_boundaries.py || { echo -e "${RED}Step 12 failed!${NC}"; exit 1; }

# Step 13
echo -e "${YELLOW}[14/19] Cleaning up again...${NC}"
python3 manual-run/step_13_cleanup_again.py || { echo -e "${RED}Step 13 failed!${NC}"; exit 1; }

# Step 14
echo -e "${YELLOW}[15/19] Building diagram...${NC}"
python3 manual-run/step_14_build_diagram.py || { echo -e "${RED}Step 14 failed!${NC}"; exit 1; }

# Step 15
echo -e "${YELLOW}[16/19] Auto-detecting public resources...${NC}"
python3 manual-run/step_15_auto_detect_public.py || { echo -e "${RED}Step 15 failed!${NC}"; exit 1; }

# Step 16
echo -e "${YELLOW}[17/19] Querying outermost boundaries...${NC}"
python3 manual-run/step_16_outermost_boundaries.py || { echo -e "${RED}Step 16 failed!${NC}"; exit 1; }

# Step 17
echo -e "${YELLOW}[18/19] Adding connections...${NC}"
python3 manual-run/step_17_connections.py || { echo -e "${RED}Step 17 failed!${NC}"; exit 1; }

# Step 18
echo -e "${YELLOW}[19/19] Exporting results...${NC}"
python3 manual-run/step_18_export.py || { echo -e "${RED}Step 18 failed!${NC}"; exit 1; }

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All steps completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
