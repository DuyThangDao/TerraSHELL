#!/usr/bin/env python3
"""
Step 04: Run implicit dependency resolution
"""
import sys
import os
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from implicit import run_implicit_dependency_resolution
from shared_state import get_in_path, get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 04] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_04.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main(
    enable_enrich=True,
    enable_exact=True,
    enable_boundary=True,
    enable_fuzzy=True
):
    """
    Step 04: Run implicit dependency resolution
    
    Args:
        enable_enrich: Enable Step 1 (Enrich Graph + Taint Analysis) (default: True)
        enable_exact: Enable Step 2 (Exact Matching) (default: True)
        enable_boundary: Enable Step 3 (Boundary-aware Matching) (default: True)
        enable_fuzzy: Enable Step 4 (Fuzzy Matching) (default: True)
    """
    logger.info("="*80)
    logger.info("STEP 04: IMPLICIT DEPENDENCY RESOLUTION")
    logger.info("="*80)
    
    # Check if implicit resolver is enabled via environment variable
    if os.getenv("ENABLE_IMPLICIT_RESOLVER", "true").lower() == "false":
        logger.info("Implicit resolver is disabled via ENABLE_IMPLICIT_RESOLVER=false")
        logger.info("Skipping Step 04...")
        return
    
    try:
        # Get paths from state
        in_path = get_in_path()
        pathID = get_path_id()
        
        if not in_path:
            logger.error("in_path not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Project path: {in_path}")
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Enrich: {enable_enrich}")
        logger.info(f"Exact: {enable_exact}")
        logger.info(f"Boundary: {enable_boundary}")
        logger.info(f"Fuzzy: {enable_fuzzy}")
        
        start_time = time.time()
        
        logger.info("Starting implicit dependency resolution...")
        logger.info("This step may take a while, especially for large projects...")
        
        results = run_implicit_dependency_resolution(
            project_path=in_path,
            path_id=pathID,
            enable_enrich=enable_enrich,
            enable_exact=enable_exact,
            enable_boundary=enable_boundary,
            enable_fuzzy=enable_fuzzy
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Implicit dependency resolution completed!")
        logger.info(f"  Results: {results}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 04 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 04: {e}", exc_info=True)
        logger.error("This step may timeout if:")
        logger.error("  1. Graph is very large")
        logger.error("  2. Database queries are slow")
        logger.error("  3. Fuzzy matching takes too long")
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
