#!/usr/bin/env python3
"""
Step 03: Load graph from Terraform folder
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph import LoadFromFolder
from shared_state import get_in_path, set_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 03] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_03.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(reinit=True):
    """
    Step 03: Load graph from Terraform folder
    
    Args:
        reinit: Có re-init Terraform project không (default: True)
    """
    logger.info("="*80)
    logger.info("STEP 03: LOAD GRAPH FROM TERRAFORM FOLDER")
    logger.info("="*80)
    
    try:
        # Get input path from state
        in_path = get_in_path()
        if not in_path:
            logger.error("in_path not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        logger.info(f"Input path: {in_path}")
        logger.info(f"Reinit: {reinit}")
        
        start_time = time.time()
        
        logger.info("Loading graph from folder...")
        logger.info("This step may take a while for large projects...")
        
        pathID = LoadFromFolder(in_path, init=reinit)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Graph loaded successfully!")
        logger.info(f"  Path ID: {pathID}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        # Save pathID to state
        set_path_id(pathID)
        logger.info(f"✓ Path ID saved to state")
        
        logger.info("="*80)
        logger.info("STEP 03 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 03: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Terraform project is very large")
        logger.error("  2. Database connection is slow")
        logger.error("  3. Terraform init/plan takes too long")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
