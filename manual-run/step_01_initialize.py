#!/usr/bin/env python3
"""
Step 01: Initialize và load configuration files
"""
import os
import sys
import logging
import fire
from pathlib import Path

# Add parent directory to path để import các module
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.yaml_importer import read_config
from shared_state import (
    set_in_path, set_out_path, set_anno, set_rule, 
    set_compresses, set_publics, set_global_tb_name, set_graph_mode,
    clear_state
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 01] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_01.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def GenerateDockerPath(folderPath: str) -> str:
    """Convert Windows path to Docker path if needed"""
    if '\\' in folderPath:
        folderPath = folderPath.replace('\\', '/')
    pathComponents = folderPath.split("/")
    for i in range(len(pathComponents) - 1, -1, -1):
        currentPath = "/".join(pathComponents[i:])
        dockerPath = os.path.join("/project", currentPath)
        if os.path.exists(dockerPath):
            return dockerPath + "/"
    return folderPath

def main(
    in_path,
    anno_path="./input/aws_annotation.yaml",
    rule_path="./input/aws_rule.yaml",
    out_path="./output",
    global_tb_name="Cloud",
    graph_mode=False,
    clear_previous_state=False
):
    """
    Step 01: Initialize và load configuration files
    
    Args:
        in_path: Đường dẫn đến Terraform project
        anno_path: Đường dẫn đến annotation file (default: ./input/aws_annotation.yaml)
        rule_path: Đường dẫn đến rule file (default: ./input/aws_rule.yaml)
        out_path: Đường dẫn output (default: ./output)
        global_tb_name: Tên global trust boundary (default: Cloud)
        graph_mode: Export graph thay vì sparta (default: False)
        clear_previous_state: Xóa state cũ trước khi chạy (default: False)
    """
    logger.info("="*80)
    logger.info("STEP 01: INITIALIZE AND LOAD CONFIGURATION FILES")
    logger.info("="*80)
    
    try:
        # Clear previous state nếu được yêu cầu
        if clear_previous_state:
            logger.info("Clearing previous state...")
            clear_state()
        
        # Handle Docker environment
        if os.getenv("DOCKER_ENV") == "1":
            in_path = GenerateDockerPath(in_path)
            out_path = "/output"
            logger.info(f"Docker environment detected. Adjusted paths:")
            logger.info(f"  in_path: {in_path}")
            logger.info(f"  out_path: {out_path}")
        
        logger.info(f"Input path: {in_path}")
        logger.info(f"Output path: {out_path}")
        logger.info(f"Annotation file: {anno_path}")
        logger.info(f"Rule file: {rule_path}")
        
        # Validate input path
        if not os.path.exists(in_path):
            logger.error(f"Input path does not exist: {in_path}")
            sys.exit(1)
        
        # Load annotation config
        logger.info("Loading annotation configuration...")
        if not os.path.exists(anno_path):
            logger.error(f"Annotation file does not exist: {anno_path}")
            sys.exit(1)
        anno = read_config(anno_path)
        logger.info(f"✓ Loaded annotation config with keys: {list(anno.keys())}")
        
        # Load rule config
        logger.info("Loading rule configuration...")
        if not os.path.exists(rule_path):
            logger.error(f"Rule file does not exist: {rule_path}")
            sys.exit(1)
        rule = read_config(rule_path)
        logger.info(f"✓ Loaded rule config with keys: {list(rule.keys())}")
        
        # Extract compresses list
        logger.info("Extracting compress list from annotation...")
        compresses = (
            [m["tf_name"] for c in anno["processes"] for m in c["members"] if m.get("compress", False)] +
            [m["tf_name"] for c in anno["data_stores"] for m in c["members"] if m.get("compress", False)]
        )
        logger.info(f"✓ Found {len(compresses)} resources to compress: {compresses}")
        
        # Extract publics set
        logger.info("Extracting public resources list from annotation...")
        publics = set(
            [m["tf_name"] for c in anno["processes"] for m in c["members"] if m.get("can_public", False)] +
            [m["tf_name"] for c in anno["data_stores"] for m in c["members"] if m.get("can_public", False)]
        )
        logger.info(f"✓ Found {len(publics)} public resource patterns: {publics}")
        
        # Save all to state
        logger.info("Saving state...")
        set_in_path(in_path)
        set_out_path(out_path)
        set_anno(anno)
        set_rule(rule)
        set_compresses(compresses)
        set_publics(publics)
        set_global_tb_name(global_tb_name)
        set_graph_mode(graph_mode)
        
        logger.info("="*80)
        logger.info("STEP 01 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        logger.info("State saved. Ready for Step 02.")
        
    except Exception as e:
        logger.error(f"ERROR in Step 01: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    fire.Fire(main)
