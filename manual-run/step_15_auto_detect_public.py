#!/usr/bin/env python3
"""
Step 15: Auto-detect public resources
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dfdgraph.component import COMPONENT_ID_NODE
from utils.auto_detect_public_resources import auto_detect_public_resources
from shared_state import get_in_path, get_path_id
import step_14_build_diagram as step14_module

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 15] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_15.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 15: Auto-detect public resources
    
    This step automatically detects EC2/RDS resources with public access.
    """
    logger.info("="*80)
    logger.info("STEP 15: AUTO-DETECT PUBLIC RESOURCES")
    logger.info("="*80)
    
    try:
        # Get data from state
        in_path = get_in_path()
        pathID = get_path_id()
        
        if not in_path:
            logger.error("in_path not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        # Check if diagram exists from step 14
        if step14_module.diagram is None:
            logger.error("Diagram not found. Please run Step 14 first.")
            sys.exit(1)
        
        diag = step14_module.diagram
        
        logger.info(f"Input path: {in_path}")
        logger.info(f"Path ID: {pathID}")
        
        start_time = time.time()
        
        logger.info("Auto-detecting public resources...")
        try:
            auto_public_ids = auto_detect_public_resources(in_path, pathID)
            logger.info(f"Found {len(auto_public_ids)} auto-detected public resources")
            
            for resource_id in auto_public_ids:
                if resource_id in COMPONENT_ID_NODE:
                    resource_node = COMPONENT_ID_NODE[resource_id]
                    diag.AddPublicNode(resource_node)
                    logger.info(f"  ✓ Auto-marked as public: {resource_node.name} (ID: {resource_id})")
                else:
                    logger.warning(f"  Resource ID {resource_id} not found in COMPONENT_ID_NODE")
            
            elapsed_time = time.time() - start_time
            logger.info(f"✓ Auto-detection completed!")
            logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.warning(f"Error in auto-detect public resources: {e}")
            logger.warning("Continuing without auto-detection...")
        
        logger.info("="*80)
        logger.info("STEP 15 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 15: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
