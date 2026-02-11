#!/usr/bin/env python3
"""
Step 06: Remove non-tagged nodes
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import RemoveNonTaggedOptimized
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 06] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_06.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(max_final_depth=20, progressive_step=2, max_iterations=100):
    """
    Step 06: Remove non-tagged nodes (OPTIMIZED VERSION)
    
    This step removes nodes that are not tagged, which helps optimize the graph.
    Uses optimized version with progressive depth and smart pre-filtering.
    
    Args:
        max_final_depth: Maximum depth to check paths (default: 20)
        progressive_step: Step size to increase depth (default: 2)
        max_iterations: Maximum iterations to prevent infinite loop (default: 100)
    """
    logger.info("="*80)
    logger.info("STEP 06: REMOVE NON-TAGGED NODES (OPTIMIZED)")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Max final depth: {max_final_depth}")
        logger.info(f"Progressive step: {progressive_step}")
        logger.info("Removing non-tagged nodes...")
        
        start_time = time.time()
        
        RemoveNonTaggedOptimized(
            pathID,
            max_final_depth=max_final_depth,
            progressive_step=progressive_step,
            max_iterations=max_iterations
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Non-tagged nodes removed!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 06 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 06: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Graph is very large")
        logger.error("  2. Database queries are slow")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
