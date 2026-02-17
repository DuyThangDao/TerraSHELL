#!/usr/bin/env python3
"""
Step 04a: Enrich Graph (Properties Only) - Phase 1.5a

This step ONLY enriches properties (decodes variables/locals) and stores them
in nodes. It does NOT create any edges.

Should run BEFORE Tag/RemoveNonTagged to ensure all nodes have enriched
properties before non-tagged nodes are deleted.
"""
import sys
import os
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from implicit import run_implicit_enrich_only
from shared_state import get_in_path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 04a] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_04a.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 04a: Enrich Graph (Properties Only)
    
    This step scans Terraform files, decodes variables/locals, and stores
    resolved properties in graph nodes. No edges are created.
    """
    logger.info("="*80)
    logger.info("STEP 04a: ENRICH GRAPH (Properties Only)")
    logger.info("="*80)
    
    # Check if implicit resolver is enabled via environment variable
    if os.getenv("ENABLE_IMPLICIT_RESOLVER", "true").lower() == "false":
        logger.info("Implicit resolver is disabled via ENABLE_IMPLICIT_RESOLVER=false")
        logger.info("Skipping Step 04a...")
        return
    
    try:
        # Get project path from state
        in_path = get_in_path()
        
        if not in_path:
            logger.error("in_path not found in state. Please run Step 01 first.")
            sys.exit(1)
        
        logger.info(f"Project path: {in_path}")
        logger.info("Enriching graph properties (no edges will be created)...")
        
        start_time = time.time()
        
        results = run_implicit_enrich_only(project_path=in_path)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Graph enrichment completed!")
        logger.info(f"  Results: {results}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 04a COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 04a: {e}", exc_info=True)
        logger.error("This step may fail if:")
        logger.error("  1. Terraform files cannot be parsed")
        logger.error("  2. Database connection fails")
        sys.exit(1)

if __name__ == '__main__':
    main()
