#!/usr/bin/env python3
"""
Step 09: Link tagged nodes

Uses In-memory BFS + Transitive Reduction approach:
- Pull graph data from Memgraph into Python memory
- BFS to compute reachability between tagged nodes
- Transitive Reduction to find direct links only
- Batch write results back to Memgraph

This is orders of magnitude faster than Cypher variable-length path matching
while producing 100% identical results.
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.n4j_helper import LinkTaggedBFS
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

def main(batch_size=500):
    """
    Step 09: Link tagged nodes (BFS + TRANSITIVE REDUCTION)
    
    This step creates direct links between tagged resource nodes.
    
    Algorithm:
    1. Pull all tagged nodes and REF edges from Memgraph into memory
    2. Build adjacency list (in-memory graph)
    3. BFS from each tagged node to find all reachable tagged nodes
    4. Transitive Reduction: keep only direct links (no intermediate tagged node)
    5. Batch MERGE the direct links back to Memgraph
    
    Guarantees 100% accuracy identical to the original Cypher query.
    
    Args:
        batch_size: Number of edges to MERGE per batch (default: 500)
    """
    logger.info("=" * 80)
    logger.info("STEP 09: LINK TAGGED NODES (BFS + TRANSITIVE REDUCTION)")
    logger.info("=" * 80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        logger.info(f"Batch size: {batch_size}")
        logger.info("Linking tagged nodes using In-memory BFS + Transitive Reduction...")
        
        start_time = time.time()
        
        LinkTaggedBFS(pathID, batch_size=batch_size)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Tagged nodes linked!")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("=" * 80)
        logger.info("STEP 09 COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 09: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    import fire
    fire.Fire(main)
