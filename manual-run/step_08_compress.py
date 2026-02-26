#!/usr/bin/env python3
"""
Step 08: Compress nodes
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import CompressV2BFS, Cleanup
from shared_state import get_compresses, get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 08] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_08.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 08: Compress nodes (BFS VERSION)
    
    This step compresses multiple nodes matching the same pattern into a single node.
    Uses CompressV2BFS which:
    - Same sequential logic as CompressV2 (proven correct)
    - Uses BFS in memory instead of Cypher variable-length path (much faster, no timeout)
    - Pulls graph into memory once, then processes sequentially
    - Cleanup only once at the end
    """
    logger.info("="*80)
    logger.info("STEP 08: COMPRESS NODES (BFS)")
    logger.info("="*80)
    
    try:
        # Get data from state
        compresses = get_compresses()
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Resources to compress: {compresses}")
        
        if not compresses:
            logger.info("No resources to compress. Skipping...")
            return
        
        start_time = time.time()
        
        for i, compress in enumerate(compresses, 1):
            logger.info(f"[{i}/{len(compresses)}] Compressing: {compress}")
            compress_start = time.time()
            
            CompressV2BFS(compress, pathID)
            
            # Note: Cleanup is called inside CompressV2BFS (once at the end)
            
            compress_elapsed = time.time() - compress_start
            logger.info(f"  ✓ Compressed {compress} in {compress_elapsed:.2f} seconds")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ All compressions completed!")
        logger.info(f"  Total time: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 08 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 08: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Many resources need compression")
        logger.error("  2. Compression queries are slow")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
