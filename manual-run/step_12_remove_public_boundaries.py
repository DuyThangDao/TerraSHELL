#!/usr/bin/env python3
"""
Step 12: Remove public boundaries
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import RemovePublicBoundaries
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 12] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_12.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 12: Remove public boundaries
    
    This step removes public boundaries and connects their sources to destinations directly.
    """
    logger.info("="*80)
    logger.info("STEP 12: REMOVE PUBLIC BOUNDARIES")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info("Removing public boundaries...")
        
        start_time = time.time()
        
        RemovePublicBoundaries(pathID)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Public boundaries removed!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 12 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 12: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
