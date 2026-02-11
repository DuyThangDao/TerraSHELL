#!/usr/bin/env python3
"""
Step 17: Query all connections and add edges
"""
import sys
import logging
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dfdgraph.component import COMPONENT_ID_NODE
from utils.n4j_helper import QueryAllConnectionResource
from shared_state import get_path_id

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [STEP 17] - %(message)s',
    handlers=[
        logging.FileHandler('manual-run/step_17.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Step 17: Query all connections and add edges
    
    This step queries all connections between resources and adds them to the diagram.
    """
    logger.info("="*80)
    logger.info("STEP 17: QUERY ALL CONNECTIONS")
    logger.info("="*80)
    
    try:
        # Get pathID from state
        pathID = get_path_id()
        
        if not pathID:
            logger.error("pathID not found in state. Please run Step 03 first.")
            sys.exit(1)
        
        logger.info(f"Path ID: {pathID}")
        
        start_time = time.time()
        
        logger.info("Querying all connections...")
        connections = QueryAllConnectionResource(pathID)
        logger.info(f"Found {len(connections)} connections")
        
        for i, r in enumerate(connections, 1):
            crafted_name1 = "%s (%s)" % (r["group1"], r["general_name1"])
            crafted_name2 = "%s (%s)" % (r["group2"], r["general_name2"])
            
            if i <= 10 or i % 100 == 0:  # Log first 10 and every 100th
                logger.info(f"  [{i}/{len(connections)}] {crafted_name1} --> {crafted_name2}")
            
            node1 = COMPONENT_ID_NODE.get(str(r["id1"]))
            node2 = COMPONENT_ID_NODE.get(str(r["id2"]))
            
            if node1 and node2:
                node1.AddEdge(node2)
            else:
                if not node1:
                    logger.warning(f"  Node1 not found: {r['id1']}")
                if not node2:
                    logger.warning(f"  Node2 not found: {r['id2']}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"✓ All connections added!")
        logger.info(f"  Total connections: {len(connections)}")
        logger.info(f"  Time taken: {elapsed_time:.2f} seconds")
        
        logger.info("="*80)
        logger.info("STEP 17 COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"ERROR in Step 17: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
