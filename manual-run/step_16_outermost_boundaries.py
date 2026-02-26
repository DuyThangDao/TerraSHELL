#!/usr/bin/env python3
"""
Step 16: Query outermost boundaries
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dfdgraph import TrustBoundary
from dfdgraph.trustboundary import BOUNDARY_ID_NODE
from utils.n4j_helper import QueryOutermostBoundary
from shared_state import get_path_id, get_diagram
import step_14_build_diagram as step14_module

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 16] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_16.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 16: Query outermost boundaries
    
    This step queries and adds outermost boundaries to the diagram.
    """
    logger.info("="*80)
    logger.info("STEP 16: QUERY OUTERMOST BOUNDARIES")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        # Check if diagram exists from step 14
        # First try module-level variable (for same-process access)
        if step14_module.aws is not None:
            aws = step14_module.aws
        else:
            # Fallback to shared_state pickle file (for cross-process access)
            diag, compos, aws = get_diagram()
            if aws is None:
                logger.error("Diagram not found. Please run Step 14 first.")
                sys.exit(1)
            # Also update module-level variables for consistency
            step14_module.diagram = diag
            step14_module.compos = compos
            step14_module.aws = aws
            logger.info("Loaded diagram from shared state file")
        
        logger.info(f"Path ID: {pathID}")
        
        start_time = time.time()
        
        logger.info("Querying outermost boundaries...")
        outermost_boundaries = QueryOutermostBoundary(pathID)
        logger.info(f"Found {len(outermost_boundaries)} outermost boundaries")
        
        for r in outermost_boundaries:
            id_ = str(r["id"])
            crafted_name = "%s (%s)" % (r["group"], r["general_name"])
            logger.info(f"  {id_} - {crafted_name}")
            
            # Create TrustBoundary if it doesn't exist
            boundary = BOUNDARY_ID_NODE.get(id_) if id_ in BOUNDARY_ID_NODE else TrustBoundary(id_, crafted_name)
            aws.AddInnerBound(boundary)
            logger.info(f"  ✓ Added outermost boundary: {crafted_name}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ Outermost boundaries added!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 16 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 16: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
