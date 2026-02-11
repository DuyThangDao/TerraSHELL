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

from utils.n4j_helper import CompressV2Hybrid, Cleanup
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

def main(max_path_length=20):
    """
    Step 08: Compress nodes (HYBRID OPTIMIZED VERSION)
    
    This step compresses multiple nodes matching the same pattern into a single node.
    Uses Hybrid Approach with:
    - Direct Relationships First
    - Progressive Path Length với Early Stop
    - Optimize Query Order
    
    Args:
        max_path_length: Độ dài path tối đa để thử progressive (default: 20)
                        Sau đó sẽ fallback về unbounded nếu cần
    """
    logger.info("="*80)
    logger.info("STEP 08: COMPRESS NODES (HYBRID OPTIMIZED)")
    logger.info("="*80)
    
    try:
        # Get data from state
        compresses = get_compresses()
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Max path length: {max_path_length}")
        logger.info(f"Resources to compress: {compresses}")
        
        if not compresses:
            logger.info("No resources to compress. Skipping...")
            return
        
        start_time = time.time()
        
        for i, compress in enumerate(compresses, 1):
            logger.info(f"[{i}/{len(compresses)}] Compressing: {compress}")
            compress_start = time.time()
            
            # Sử dụng Hybrid version với tất cả optimizations
            CompressV2Hybrid(compress, pathID, max_path_length=max_path_length)
            
            # Note: Cleanup đã được gọi bên trong CompressV2Hybrid nếu cần
            
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
