#!/usr/bin/env python3
"""
Step 09: Link tagged nodes
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import LinkTaggedOptimized
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 09] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_09.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(max_path_length=20, limit_per_iteration=50, max_iterations=1000):
    """
    Step 09: Link tagged nodes (OPTIMIZED VERSION)
    
    This step creates direct links between tagged nodes.
    Uses Hybrid Approach with:
    - Progressive Path Length: Xử lý paths ngắn trước (nhanh)
    - Query gốc với LIMIT + Loop: Xử lý paths dài và đảm bảo 100% accuracy
    
    Args:
        max_path_length: Độ dài path tối đa để thử progressive (default: 20)
        limit_per_iteration: Số lượng links để xử lý mỗi iteration trong fallback (default: 50)
        max_iterations: Số lần lặp tối đa trong fallback để tránh infinite loop (default: 1000)
    """
    logger.info("="*80)
    logger.info("STEP 09: LINK TAGGED NODES (OPTIMIZED)")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Max path length: {max_path_length}")
        logger.info(f"Limit per iteration: {limit_per_iteration}")
        logger.info(f"Max iterations: {max_iterations}")
        logger.info("Linking tagged nodes...")
        logger.info("This step may take a while for large graphs...")
        
        start_time = time.time()
        
        LinkTaggedOptimized(pathID, max_path_length=max_path_length, limit_per_iteration=limit_per_iteration, max_iterations=max_iterations)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Tagged nodes linked!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 09 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 09: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Graph is very large")
        logger.error("  2. Link queries are slow")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
