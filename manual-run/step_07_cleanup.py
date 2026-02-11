#!/usr/bin/env python3
"""
Step 07: Cleanup graph (remove self-loops, etc.)
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import Cleanup
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 07] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_07.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 07: Cleanup graph
    
    This step removes self-loops and other graph inconsistencies.
    """
    logger.info("="*80)
    logger.info("STEP 07: CLEANUP GRAPH")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info("Cleaning up graph...")
        
        start_time = time.time()
        
        Cleanup(pathID)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Graph cleanup completed!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 07 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 07: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
