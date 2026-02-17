#!/usr/bin/env python3
"""
Step 04b: Implicit Matching (Edges Only) - Phase 1.5b

This step ONLY creates REF edges between tagged nodes based on matching
algorithms (Exact, Boundary-aware, Fuzzy). It does NOT enrich properties.

Should run AFTER Compress to ensure edges are created at the compressed level,
not at granular resource level.
"""
import sys
import os
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from implicit import run_implicit_matching_only
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 04b] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_04b.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(
    enable_exact=True,
    enable_boundary=True,
    enable_fuzzy=True
):
    """
    Step 04b: Implicit Matching (Edges Only)
    
    Args:
        enable_exact: Enable Exact Matching (default: True)
        enable_boundary: Enable Boundary-aware Matching (default: True)
        enable_fuzzy: Enable Fuzzy Matching (default: True)
    """
    logger.info("="*80)
    logger.info("STEP 04b: IMPLICIT MATCHING (Edges Only)")
    logger.info("="*80)
    
    # Check if implicit resolver is enabled via environment variable
    if os.getenv("ENABLE_IMPLICIT_RESOLVER", "true").lower() == "false":
        logger.info("Implicit resolver is disabled via ENABLE_IMPLICIT_RESOLVER=false")
        logger.info("Skipping Step 04b...")
        return
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Exact: {enable_exact}")
        logger.info(f"Boundary: {enable_boundary}")
        logger.info(f"Fuzzy: {enable_fuzzy}")
        logger.info("Creating implicit edges between tagged nodes...")
        
        start_time = time.time()
        
        results = run_implicit_matching_only(
            path_id=pathID,
            enable_exact=enable_exact,
            enable_boundary=enable_boundary,
            enable_fuzzy=enable_fuzzy
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Implicit matching completed!")
        logger.info(f"  Results: {results}")
        logger.info(f"  Total links created: {results.get('exact', 0) + results.get('boundary', 0) + results.get('fuzzy', 0)}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 04b COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 04b: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Graph is very large")
        logger.error("  2. Database queries are slow")
        logger.error("  3. Fuzzy matching takes too long")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
